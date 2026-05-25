import asyncio
from datetime import datetime, timezone

from app.domain.models import Candle
from app.services.backtest_jobs import BacktestJobService
from app.services.backtest_scheduler import AutoBacktestScheduler


def _sample_candles(n: int = 30) -> list[Candle]:
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    out: list[Candle] = []
    price = 100.0
    for i in range(n):
        nxt = price + (1 if i % 2 == 0 else -0.5)
        out.append(
            Candle(
                open=price,
                high=max(price, nxt) + 0.2,
                low=min(price, nxt) - 0.2,
                close=nxt,
                ts=base,
                volume=1000 + i,
            )
        )
        price = nxt
    return out


def test_auto_backtest_scheduler_trigger_if_due_once_per_day():
    async def scenario() -> None:
        now = datetime(2026, 1, 1, 16, 30, tzinfo=timezone.utc)
        service = BacktestJobService()
        scheduler = AutoBacktestScheduler(
            backtest_service=service,
            candles_provider=lambda: _sample_candles(40),
            now_fn=lambda: now,
            enabled=True,
            run_hour=16,
        )
        first = await scheduler.trigger_if_due()
        second = await scheduler.trigger_if_due()
        assert first["triggered"] is True
        assert second["triggered"] is False
        assert second["reason"] == "already_ran_today"
        assert scheduler.last_job_id is not None

    asyncio.run(scenario())


def test_auto_backtest_scheduler_manual_trigger():
    async def scenario() -> None:
        service = BacktestJobService()
        scheduler = AutoBacktestScheduler(
            backtest_service=service,
            candles_provider=lambda: _sample_candles(20),
            enabled=False,
        )
        result = await scheduler.trigger_now(reason="manual_test")
        assert result["triggered"] is True
        assert result["reason"] == "manual_test"
        assert scheduler.status()["last_status"] == "triggered"

    asyncio.run(scenario())


def test_auto_backtest_scheduler_records_last_job_snapshot():
    async def scenario() -> None:
        service = BacktestJobService()
        scheduler = AutoBacktestScheduler(
            backtest_service=service,
            candles_provider=lambda: _sample_candles(25),
            enabled=True,
            run_hour=0,
            now_fn=lambda: datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        )
        result = await scheduler.trigger_if_due()
        assert result["triggered"] is True
        for _ in range(500):
            snap = scheduler.status().get("last_job_snapshot")
            if isinstance(snap, dict):
                break
            await asyncio.sleep(0.01)
        status = scheduler.status()
        assert status["last_job_snapshot"] is not None
        assert status["last_job_snapshot"]["status"] in {"completed", "failed"}

    asyncio.run(scenario())
