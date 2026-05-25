import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.models import Candle, Signal
from app.services.backtest_jobs import BacktestJobService


class FakeSink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, text: str) -> bool:
        self.messages.append(text)
        return True


def test_backtest_job_service_runs_async_with_progress():
    async def scenario() -> tuple[dict[str, object], list[str]]:
        sink = FakeSink()
        service = BacktestJobService(alert_sink=sink)
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        candles = [
            Candle(open=100, high=101, low=99, close=100, ts=base),
            Candle(open=102, high=103, low=101, close=103, ts=base + timedelta(minutes=5)),
            Candle(open=103, high=104, low=102, close=102, ts=base + timedelta(minutes=10)),
        ]
        signals = [
            Signal(index=0, side="buy", ticker="005930"),
            Signal(index=1, side="sell", ticker="005930"),
        ]

        job_id = await service.start_job(candles=candles, signals=signals, slippage_pct=0.05)
        final: dict[str, object] | None = None
        for _ in range(100):
            row = await service.get_job(job_id)
            assert row is not None
            if row["status"] in {"completed", "failed"}:
                final = row
                break
            await asyncio.sleep(0.001)

        assert final is not None
        return final, sink.messages

    result, messages = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert result["progress"] == 100
    assert result["result"] is not None
    assert result["result"]["trade_count"] == 2
    assert "sharpe_ratio" in result["result"]
    assert "mdd" in result["result"]
    assert "expectancy" in result["result"]
    assert "total_return_pct" in result["result"]
    assert float(result["result"]["total_return_pct"]) > 0
    assert len(messages) == 1
    assert "[백테스트 완료]" in messages[0]


def test_backtest_job_service_list_filter_and_pagination():
    async def scenario() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        service = BacktestJobService()
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        candles = [
            Candle(open=100, high=101, low=99, close=100, ts=base),
            Candle(open=101, high=102, low=100, close=101, ts=base + timedelta(minutes=5)),
        ]
        signals = [Signal(index=0, side="buy", ticker="005930")]
        ids = []
        for _ in range(3):
            ids.append(await service.start_job(candles=candles, signals=signals))

        for _ in range(200):
            rows = await service.list_jobs(limit=10)
            if all(x["status"] in {"completed", "failed"} for x in rows[:3]):
                break
            await asyncio.sleep(0.001)

        first_page = await service.list_jobs(limit=2, offset=0, status="completed")
        second_page = await service.list_jobs(limit=2, offset=2, status="completed")
        return first_page, second_page

    page1, page2 = asyncio.run(scenario())
    assert len(page1) <= 2
    assert all(x["status"] == "completed" for x in page1)
    assert all(x["status"] == "completed" for x in page2)


def test_backtest_job_service_skips_alert_for_dashboard_manual_source():
    async def scenario() -> tuple[dict[str, object], list[str]]:
        sink = FakeSink()
        service = BacktestJobService(alert_sink=sink)
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        candles = [
            Candle(open=100, high=101, low=99, close=100, ts=base),
            Candle(open=101, high=102, low=100, close=101, ts=base + timedelta(minutes=5)),
        ]
        signals = [Signal(index=0, side="buy", ticker="005930")]
        job_id = await service.start_job(
            candles=candles,
            signals=signals,
            meta={"source": "dashboard_manual"},
        )

        final: dict[str, object] | None = None
        for _ in range(100):
            row = await service.get_job(job_id)
            assert row is not None
            if row["status"] in {"completed", "failed"}:
                final = row
                break
            await asyncio.sleep(0.001)

        assert final is not None
        return final, sink.messages

    result, messages = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert result["progress"] == 100
    assert len(messages) == 0


def test_backtest_job_service_applies_stop_loss_instead_of_last_close():
    async def scenario() -> dict[str, object]:
        service = BacktestJobService()
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        candles = [
            Candle(open=100, high=102, low=98, close=100, ts=base),
            Candle(open=100, high=101, low=80, close=85, ts=base + timedelta(minutes=5)),
            Candle(open=85, high=87, low=84, close=86, ts=base + timedelta(minutes=10)),
        ]
        signals = [Signal(index=0, side="buy", ticker="005930")]
        job_id = await service.start_job(candles=candles, signals=signals, slippage_pct=0.05)
        for _ in range(100):
            row = await service.get_job(job_id)
            assert row is not None
            if row["status"] in {"completed", "failed"}:
                return row
            await asyncio.sleep(0.001)
        raise AssertionError("job timeout")

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    payload = result["result"]
    assert payload["trade_count"] == 1
    assert payload["exit_reasons"]["stop_loss"] == 1
    # entry=100.05, atr(첫 봉)=4 -> stop=94.05, stop 손실 약 -6.0
    assert payload["total_pnl"] == pytest.approx(-6.0, abs=0.02)
