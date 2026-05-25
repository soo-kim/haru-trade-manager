import asyncio
from datetime import datetime, timezone

from app.domain.models import Candle, Signal
from app.loops.core import InMemorySignalQueue, LoopBScanner
from app.loops.loop_b_runtime import LoopBRunner, MarketSchedule
from app.repositories.candle import CandleRepository
from tests.utils import build_session_factory


class FakeStrategyEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def scan(self, *, timeframe: str, ticker: str, candles: list[Candle], now: datetime) -> list[Signal]:
        self.calls.append({"timeframe": timeframe, "ticker": ticker, "count": len(candles), "now": now})
        if not candles:
            return []
        return [
            Signal(
                index=len(candles) - 1,
                side="buy",
                ticker=ticker,
                strategy_id="test",
                timeframe=timeframe,
                price=candles[-1].close,
                signal_time=now,
            )
        ]


class FakeCandleFetcher:
    def __init__(self, candles: list[Candle]) -> None:
        self.candles = candles
        self.calls: list[dict[str, object]] = []

    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[Candle]:
        self.calls.append({"ticker": ticker, "timeframe": timeframe, "since": since})
        return self.candles


def test_market_schedule_due_timeframes():
    schedule = MarketSchedule()
    assert schedule.due_timeframes(datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)) == ["5m"]
    assert schedule.due_timeframes(datetime(2026, 1, 1, 9, 15, tzinfo=timezone.utc)) == ["3m", "5m", "15m"]
    assert schedule.due_timeframes(datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)) == ["3m", "5m", "15m", "60m"]
    assert "1d" in schedule.due_timeframes(datetime(2026, 1, 1, 15, 30, tzinfo=timezone.utc))
    assert schedule.due_timeframes(datetime(2026, 1, 1, 8, 35, tzinfo=timezone.utc)) == []


def test_loop_b_runner_syncs_candles_and_dedupes_same_slot():
    maker = build_session_factory()
    repo = CandleRepository()
    ticker = "005930"
    t0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)

    with maker() as db:
        repo.upsert_incremental(
            db,
            ticker=ticker,
            timeframe="5m",
            candle_time=t0,
            open_price=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        )

    fetcher = FakeCandleFetcher(
        candles=[
            Candle(open=100, high=102, low=98, close=101, volume=1200, ts=t0),  # UPDATE
            Candle(open=101, high=103, low=100, close=102, volume=1300, ts=t1),  # INSERT
        ]
    )
    queue = InMemorySignalQueue(items=[])
    scanner = LoopBScanner(strategy_engine=FakeStrategyEngine(), queue=queue)
    runner = LoopBRunner(
        scanner=scanner,
        candle_repo=repo,
        candle_fetcher=fetcher,
        session_factory=maker,
        now_fn=lambda: t1,
    )

    produced_first = asyncio.run(runner.run_once_for_ticker(ticker))
    produced_second = asyncio.run(runner.run_once_for_ticker(ticker))

    assert produced_first == 1
    assert produced_second == 0
    assert len(fetcher.calls) == 1
    since = fetcher.calls[0]["since"]
    assert isinstance(since, datetime)
    assert since.replace(tzinfo=timezone.utc) == t0
    assert len(queue.items) == 1

    with maker() as db:
        rows = repo.list_recent(db, ticker=ticker, timeframe="5m", limit=10)
        assert len(rows) == 2
        assert rows[0].close == 101
        assert rows[1].close == 102
