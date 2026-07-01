from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.models import Candle
from app.loops.core import LoopBScanner
from app.db.models.candle import Candle as CandleRow
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository


class SessionFactory(Protocol):
    def __call__(self) -> Session:
        raise NotImplementedError


class CandleFetcher(Protocol):
    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[Candle]:
        raise NotImplementedError


@dataclass(frozen=True)
class MarketSchedule:
    def due_timeframes(self, now: datetime) -> list[str]:
        clock = now.timetz().replace(tzinfo=None)
        hh = clock.hour
        mm = clock.minute

        # 동시호가 구간은 스크리닝/주문 트리거를 만들지 않는다.
        if (hh == 8 and 30 <= mm < 60) or (hh == 15 and 20 <= mm < 30):
            return []

        # 장외 포함 운영 시간(08:00~20:00) 밖은 스킵
        total_minutes = (hh * 60) + mm
        if total_minutes < (8 * 60) or total_minutes > (20 * 60):
            return []

        due: list[str] = []
        if mm % 3 == 0:
            due.append("3m")
        if mm % 5 == 0:
            due.append("5m")
        if mm % 15 == 0:
            due.append("15m")
        if mm == 0:
            due.append("60m")
        if hh == 15 and mm == 30:
            due.append("1d")
        return due

    def slot_key(self, *, now: datetime, timeframe: str) -> str:
        t = now.timetz().replace(tzinfo=None)
        if timeframe == "1d":
            return now.strftime("%Y-%m-%d")
        if timeframe == "60m":
            return now.strftime("%Y-%m-%d %H:00")
        if timeframe == "15m":
            quarter = (t.minute // 15) * 15
            return now.strftime("%Y-%m-%d %H:") + f"{quarter:02d}"
        if timeframe == "3m":
            minute = (t.minute // 3) * 3
            return now.strftime("%Y-%m-%d %H:") + f"{minute:02d}"
        minute = (t.minute // 5) * 5
        return now.strftime("%Y-%m-%d %H:") + f"{minute:02d}"


class LoopBRunner:
    """
    Loop B runtime:
    - 봉마감 판단
    - 증분 캔들 동기화(UPDATE/INSERT)
    - 전략 스캔 후 시그널 큐 적재
    """

    def __init__(
        self,
        *,
        scanner: LoopBScanner,
        candle_repo: CandleRepository,
        candle_fetcher: CandleFetcher,
        session_factory: SessionFactory,
        now_fn: Callable[[], datetime],
        schedule: MarketSchedule | None = None,
        collection_state_repo: CandleCollectionStateRepository | None = None,
        collection_source: str = "loop_b",
    ) -> None:
        self.scanner = scanner
        self.candle_repo = candle_repo
        self.candle_fetcher = candle_fetcher
        self.session_factory = session_factory
        self.now_fn = now_fn
        self.schedule = schedule or MarketSchedule()
        self.collection_state_repo = collection_state_repo or CandleCollectionStateRepository()
        self.collection_source = collection_source
        self._processed_slots: dict[tuple[str, str], str] = {}

    async def run_once_for_ticker(self, ticker: str) -> int:
        now = self.now_fn()
        due = self.schedule.due_timeframes(now)
        if not due:
            return 0

        produced = 0
        for timeframe in due:
            slot = self.schedule.slot_key(now=now, timeframe=timeframe)
            key = (ticker, timeframe)
            if self._processed_slots.get(key) == slot:
                continue
            try:
                produced += await self._sync_and_scan(ticker=ticker, timeframe=timeframe, now=now)
            except Exception:  # noqa: BLE001 - one ticker/timeframe failure must not stop the loop batch
                continue
            self._processed_slots[key] = slot
        return produced

    async def _sync_and_scan(self, *, ticker: str, timeframe: str, now: datetime) -> int:
        with self.session_factory() as db:
            last_ts = self.candle_repo.get_last_candle_time(db, ticker=ticker, timeframe=timeframe)

        try:
            fresh = await self.candle_fetcher.fetch_incremental(ticker=ticker, timeframe=timeframe, since=last_ts)
        except Exception as exc:  # noqa: BLE001 - record collection failure before isolating this ticker
            self._record_collection_failure(ticker=ticker, timeframe=timeframe, error=exc)
            raise

        try:
            with self.session_factory() as db:
                for candle in fresh:
                    self.candle_repo.upsert_incremental(
                        db,
                        ticker=ticker,
                        timeframe=timeframe,
                        candle_time=candle.ts,
                        open_price=candle.open,
                        high=candle.high,
                        low=candle.low,
                        close=candle.close,
                        volume=candle.volume,
                    )
                state = db.execute(
                    select(
                        func.min(CandleRow.candle_time).label("first_candle_time"),
                        func.max(CandleRow.candle_time).label("last_candle_time"),
                        func.count(CandleRow.id).label("row_count"),
                    ).where(CandleRow.ticker == ticker, CandleRow.timeframe == timeframe)
                ).one()
                self.collection_state_repo.record_success(
                    db,
                    ticker=ticker,
                    timeframe=timeframe,
                    first_candle_time=state.first_candle_time,
                    last_candle_time=state.last_candle_time,
                    row_count=int(state.row_count or 0),
                    source=self.collection_source,
                    collected_at=self.now_fn(),
                )
                rows = self.candle_repo.list_recent(db, ticker=ticker, timeframe=timeframe, limit=240)
        except SQLAlchemyError as exc:
            self._record_collection_failure(ticker=ticker, timeframe=timeframe, error=exc)
            raise

        domain_candles = [
            Candle(
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
                ts=row.candle_time,
            )
            for row in rows
        ]
        return self.scanner.run_for_timeframe(timeframe=timeframe, ticker=ticker, candles=domain_candles, now=now)

    def _record_collection_failure(self, *, ticker: str, timeframe: str, error: Exception) -> None:
        try:
            with self.session_factory() as db:
                self.collection_state_repo.record_failure(
                    db,
                    ticker=ticker,
                    timeframe=timeframe,
                    error=str(error) or error.__class__.__name__,
                    source=self.collection_source,
                    failed_at=self.now_fn(),
                )
        except SQLAlchemyError:
            return
