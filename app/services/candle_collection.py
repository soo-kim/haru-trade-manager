from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy import func, select

from app.db.models.candle import Candle
from app.domain.models import Candle as DomainCandle
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository


class CandleFetcher(Protocol):
    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[DomainCandle]: ...


class CandleCollectionService:
    def __init__(
        self,
        *,
        session_factory,
        candle_repo: CandleRepository | None = None,
        state_repo: CandleCollectionStateRepository | None = None,
        fetcher: CandleFetcher,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.candle_repo = candle_repo or CandleRepository()
        self.state_repo = state_repo or CandleCollectionStateRepository()
        self.fetcher = fetcher
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    async def collect_initial(
        self,
        *,
        tickers: Sequence[str],
        timeframes: Sequence[str],
        source: str = "unknown",
    ) -> dict[str, Any]:
        return await self._collect(mode="initial", tickers=tickers, timeframes=timeframes, source=source)

    async def collect_incremental(
        self,
        *,
        tickers: Sequence[str],
        timeframes: Sequence[str],
        source: str = "unknown",
    ) -> dict[str, Any]:
        return await self._collect(mode="incremental", tickers=tickers, timeframes=timeframes, source=source)

    async def recollect(
        self,
        *,
        ticker: str,
        timeframe: str,
        source: str = "unknown",
    ) -> dict[str, Any]:
        return await self._collect(mode="recollect", tickers=[ticker], timeframes=[timeframe], source=source)

    async def _collect(
        self,
        *,
        mode: str,
        tickers: Sequence[str],
        timeframes: Sequence[str],
        source: str,
    ) -> dict[str, Any]:
        processed = 0
        failed = 0
        inserted = 0
        updated = 0
        errors: list[str] = []
        for ticker in tickers:
            clean_ticker = ticker.strip()
            if not clean_ticker:
                continue
            for timeframe in timeframes:
                clean_timeframe = timeframe.strip()
                if not clean_timeframe:
                    continue
                try:
                    since = None if mode in {"initial", "recollect"} else self._last_candle_time(clean_ticker, clean_timeframe)
                    candles = await self.fetcher.fetch_incremental(
                        ticker=clean_ticker,
                        timeframe=clean_timeframe,
                        since=since,
                    )
                    inserted_count, updated_count = self._upsert_and_record_success(
                        ticker=clean_ticker,
                        timeframe=clean_timeframe,
                        candles=candles,
                        source=source,
                    )
                    inserted += inserted_count
                    updated += updated_count
                    processed += 1
                except Exception as exc:  # noqa: BLE001 - batch must record partial failures and continue
                    failed += 1
                    message = str(exc) or exc.__class__.__name__
                    errors.append(f"{clean_ticker}:{clean_timeframe}:{message}")
                    with self.session_factory() as db:
                        self.state_repo.record_failure(
                            db,
                            ticker=clean_ticker,
                            timeframe=clean_timeframe,
                            error=message,
                            source=source,
                            failed_at=self.now_fn(),
                        )
        return {
            "ok": failed == 0,
            "mode": mode,
            "processed_count": processed,
            "failed_count": failed,
            "inserted": inserted,
            "updated": updated,
            "errors": errors,
        }

    def _last_candle_time(self, ticker: str, timeframe: str) -> datetime | None:
        with self.session_factory() as db:
            return db.scalar(select(func.max(Candle.candle_time)).where(Candle.ticker == ticker, Candle.timeframe == timeframe))

    def _upsert_and_record_success(
        self,
        *,
        ticker: str,
        timeframe: str,
        candles: Sequence[DomainCandle],
        source: str,
    ) -> tuple[int, int]:
        payload = [
            {
                "candle_time": c.ts,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        with self.session_factory() as db:
            inserted = 0
            updated = 0
            if payload:
                inserted, updated = self.candle_repo.upsert_batch(db, ticker=ticker, timeframe=timeframe, candles=payload)
            row = db.execute(
                select(
                    func.min(Candle.candle_time).label("first_candle_time"),
                    func.max(Candle.candle_time).label("last_candle_time"),
                    func.count(Candle.id).label("row_count"),
                ).where(Candle.ticker == ticker, Candle.timeframe == timeframe)
            ).one()
            after = int(row.row_count or 0)
            self.state_repo.record_success(
                db,
                ticker=ticker,
                timeframe=timeframe,
                first_candle_time=row.first_candle_time,
                last_candle_time=row.last_candle_time,
                row_count=after,
                source=source,
                collected_at=self.now_fn(),
            )
            return inserted, updated
