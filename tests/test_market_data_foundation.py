from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.models.candle import Candle
from app.db.models.market_data import CandleCollectionState
from app.domain.models import Candle as DomainCandle
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository
from app.repositories.universe import UniverseRepository
from app.services.candle_collection import CandleCollectionService
from app.services.candle_coverage import CandleCoverageService
from tests.utils import build_session, build_session_factory


class FakeFetcher:
    def __init__(self, payloads: dict[tuple[str, str], list[DomainCandle]] | None = None) -> None:
        self.payloads = payloads or {}
        self.calls: list[tuple[str, str, datetime | None]] = []
        self.failures: dict[tuple[str, str], Exception] = {}

    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[DomainCandle]:
        self.calls.append((ticker, timeframe, since))
        failure = self.failures.get((ticker, timeframe))
        if failure is not None:
            raise failure
        return self.payloads.get((ticker, timeframe), [])


def test_candle_collection_state_records_success_and_failure():
    repo = CandleCollectionStateRepository()
    now = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    first = now - timedelta(days=10)

    with build_session() as db:
        success = repo.record_success(
            db,
            ticker="005930",
            timeframe="3m",
            first_candle_time=first,
            last_candle_time=now,
            row_count=100,
            source="kiwoom",
            collected_at=now,
        )
        assert success.consecutive_error_count == 0
        assert success.last_error is None
        assert success.last_success_at == now
        assert success.first_candle_time == first
        assert success.last_candle_time == now

        failed = repo.record_failure(
            db,
            ticker="005930",
            timeframe="3m",
            error="rate_limit",
            source="kiwoom",
            failed_at=now + timedelta(minutes=1),
        )
        assert failed.last_error == "rate_limit"
        assert failed.consecutive_error_count == 1
        assert failed.last_success_at == now
        assert failed.row_count == 100

        failed_again = repo.record_failure(
            db,
            ticker="005930",
            timeframe="3m",
            error="timeout",
            source="kiwoom",
            failed_at=now + timedelta(minutes=2),
        )
        assert failed_again.last_error == "timeout"
        assert failed_again.consecutive_error_count == 2


def test_candle_coverage_service_reports_timeframe_counts_and_stale_states():
    candle_repo = CandleRepository()
    universe_repo = UniverseRepository()
    state_repo = CandleCollectionStateRepository()
    now = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    stale_cutoff = now - timedelta(days=1)

    with build_session() as db:
        universe_repo.upsert_symbol(db, ticker="005930", name="삼성전자", market="KOSPI200", in_universe=True, is_active=True)
        universe_repo.upsert_symbol(db, ticker="000660", name="SK하이닉스", market="KOSPI200", in_universe=True, is_active=True)
        universe_repo.upsert_symbol(db, ticker="035420", name="NAVER", market="KOSPI200", in_universe=True, is_active=False)
        candle_repo.upsert_batch(
            db,
            ticker="005930",
            timeframe="3m",
            candles=[
                {"candle_time": now - timedelta(minutes=6), "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
                {"candle_time": now - timedelta(minutes=3), "open": 2, "high": 3, "low": 2, "close": 3, "volume": 20},
            ],
        )
        candle_repo.upsert_batch(
            db,
            ticker="000660",
            timeframe="3m",
            candles=[{"candle_time": now - timedelta(days=3), "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}],
        )
        state_repo.record_success(
            db,
            ticker="005930",
            timeframe="3m",
            first_candle_time=now - timedelta(minutes=6),
            last_candle_time=now - timedelta(minutes=3),
            row_count=2,
            source="test",
            collected_at=now,
        )
        state_repo.record_failure(
            db,
            ticker="000660",
            timeframe="3m",
            error="network",
            source="test",
            failed_at=now,
        )

        service = CandleCoverageService(
            session_factory=lambda: db,
            universe_repo=universe_repo,
            candle_repo=candle_repo,
            state_repo=state_repo,
            now_fn=lambda: now,
        )
        report = service.coverage(timeframes=("3m", "1d"), stale_after=stale_cutoff)

    assert report["universe_count"] == 3
    tf3 = report["timeframes"]["3m"]
    assert tf3["ticker_count"] == 2
    assert tf3["missing_count"] == 1
    assert tf3["stale_count"] == 1
    assert tf3["failed_state_count"] == 1
    assert tf3["backtest_ready_count"] == 1
    assert tf3["latest_candle_time"] == (now - timedelta(minutes=3)).isoformat()
    assert report["timeframes"]["1d"]["ticker_count"] == 0


def test_candle_repository_upsert_batch_deduplicates_payload_candle_times():
    candle_repo = CandleRepository()
    now = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)

    with build_session() as db:
        inserted, updated = candle_repo.upsert_batch(
            db,
            ticker="005930",
            timeframe="3m",
            candles=[
                {"candle_time": now, "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10},
                {"candle_time": now, "open": 2, "high": 3, "low": 2, "close": 3, "volume": 20},
            ],
        )
        rows = candle_repo.list_range(db, ticker="005930", timeframe="3m")

    assert inserted == 1
    assert updated == 0
    assert len(rows) == 1
    assert rows[0].open == 2
    assert rows[0].close == 3
    assert rows[0].volume == 20


def test_candle_collection_service_separates_initial_and_incremental_collection():
    session_factory = build_session_factory()
    candle_repo = CandleRepository()
    state_repo = CandleCollectionStateRepository()
    base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    fetcher = FakeFetcher(
        {
            ("005930", "3m"): [
                DomainCandle(open=1, high=2, low=1, close=2, volume=10, ts=base),
                DomainCandle(open=2, high=3, low=2, close=3, volume=20, ts=base + timedelta(minutes=3)),
            ]
        }
    )
    service = CandleCollectionService(
        session_factory=session_factory,
        candle_repo=candle_repo,
        state_repo=state_repo,
        fetcher=fetcher,
        now_fn=lambda: base + timedelta(minutes=4),
    )

    initial = asyncio.run(service.collect_initial(tickers=["005930"], timeframes=("3m",), source="test"))
    assert initial["mode"] == "initial"
    assert initial["processed_count"] == 1
    assert initial["inserted"] == 2
    assert fetcher.calls[0] == ("005930", "3m", None)

    fetcher.payloads[("005930", "3m")] = [
        DomainCandle(open=3, high=4, low=3, close=4, volume=30, ts=base + timedelta(minutes=6))
    ]
    incremental = asyncio.run(service.collect_incremental(tickers=["005930"], timeframes=("3m",), source="test"))
    assert incremental["mode"] == "incremental"
    assert incremental["inserted"] == 1
    assert fetcher.calls[-1] == ("005930", "3m", base + timedelta(minutes=3))

    with session_factory() as db:
        rows = db.scalars(select(Candle).where(Candle.ticker == "005930").order_by(Candle.candle_time)).all()
        state = db.get(CandleCollectionState, {"ticker": "005930", "timeframe": "3m"})
        assert len(rows) == 3
        assert state is not None
        assert state.row_count == 3
        assert state.last_candle_time == base + timedelta(minutes=6)


def test_candle_collection_service_records_partial_failures_without_stopping_batch():
    session_factory = build_session_factory()
    candle_repo = CandleRepository()
    state_repo = CandleCollectionStateRepository()
    base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    fetcher = FakeFetcher({("005930", "1d"): [DomainCandle(open=1, high=1, low=1, close=1, volume=1, ts=base)]})
    fetcher.failures[("000660", "1d")] = RuntimeError("timeout")
    service = CandleCollectionService(
        session_factory=session_factory,
        candle_repo=candle_repo,
        state_repo=state_repo,
        fetcher=fetcher,
        now_fn=lambda: base,
    )

    result = asyncio.run(service.collect_incremental(tickers=["005930", "000660"], timeframes=("1d",), source="test"))

    assert result["processed_count"] == 1
    assert result["failed_count"] == 1
    assert result["ok"] is False
    assert result["errors"] == ["000660:1d:timeout"]
    with session_factory() as db:
        failed_state = db.get(CandleCollectionState, {"ticker": "000660", "timeframe": "1d"})
        assert failed_state is not None
        assert failed_state.last_error == "timeout"
        assert failed_state.consecutive_error_count == 1
