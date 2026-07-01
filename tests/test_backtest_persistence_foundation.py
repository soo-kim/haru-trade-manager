from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.db.models.backtest import BacktestEquityPoint, BacktestRun, BacktestTrade
from app.domain.models import Candle, Signal
from app.repositories.backtest import BacktestRepository
from app.services.backtest_jobs import BacktestJobService
from tests.utils import build_session_factory


def test_backtest_repository_persists_run_summary_trades_and_equity_points():
    session_factory = build_session_factory()
    repo = BacktestRepository()
    created = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
    completed = created + timedelta(seconds=3)

    with session_factory() as db:
        repo.create_run(
            db,
            run_id="run-1",
            name="manual 005930",
            strategy_id="volume_surge",
            timeframe="3m",
            start_at=created - timedelta(days=1),
            end_at=created,
            params={"k": 0.5},
            slippage_pct=0.05,
            commission_pct=0.01,
            status="queued",
            meta={"ticker": "005930", "candles": 120},
            created_at=created,
        )
        repo.mark_completed(
            db,
            run_id="run-1",
            summary={"trade_count": 1, "total_pnl": 12.5},
            completed_at=completed,
            trades=[
                {
                    "ticker": "005930",
                    "entry_signal_time": created,
                    "entry_time": created + timedelta(minutes=3),
                    "entry_price": 100.0,
                    "exit_time": created + timedelta(minutes=9),
                    "exit_price": 112.5,
                    "side": "buy",
                    "pnl": 12.5,
                    "return_pct": 0.125,
                    "exit_reason": "end_of_data",
                    "bars_held": 2,
                }
            ],
            equity_points=[{"timestamp": created + timedelta(minutes=9), "equity": 12.5, "drawdown": 0.0}],
        )

        run = db.get(BacktestRun, "run-1")
        trades = db.query(BacktestTrade).filter(BacktestTrade.run_id == "run-1").all()
        points = db.query(BacktestEquityPoint).filter(BacktestEquityPoint.run_id == "run-1").all()

    assert run is not None
    assert run.status == "completed"
    assert run.summary_json["total_pnl"] == 12.5
    assert run.meta_json["candles"] == 120
    assert len(trades) == 1
    assert trades[0].bars_held == 2
    assert len(points) == 1
    assert points[0].equity == 12.5


def test_backtest_job_service_persists_dashboard_manual_run_metadata_and_result():
    async def scenario() -> str:
        session_factory = build_session_factory()
        service = BacktestJobService(session_factory=session_factory, backtest_repo=BacktestRepository())
        base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        candles = [
            Candle(open=100, high=101, low=99, close=100, volume=10, ts=base),
            Candle(open=101, high=104, low=100, close=103, volume=20, ts=base + timedelta(minutes=3)),
            Candle(open=103, high=108, low=102, close=107, volume=30, ts=base + timedelta(minutes=6)),
        ]
        signals = [Signal(index=0, side="buy", ticker="005930", strategy_id="volume_surge", timeframe="3m", signal_time=base)]
        job_id = await service.start_job(
            candles=candles,
            signals=signals,
            slippage_pct=0.05,
            meta={
                "source": "dashboard_manual",
                "ticker": "005930",
                "strategy_id": "volume_surge",
                "timeframe": "3m",
                "start": base.isoformat(),
                "end": (base + timedelta(minutes=6)).isoformat(),
                "candles": len(candles),
                "signals": len(signals),
            },
        )
        for _ in range(100):
            row = await service.get_job(job_id)
            assert row is not None
            if row["status"] in {"completed", "failed"}:
                break
            await asyncio.sleep(0.001)
        with session_factory() as db:
            run = db.get(BacktestRun, job_id)
            trades = db.query(BacktestTrade).filter(BacktestTrade.run_id == job_id).all()
            points = db.query(BacktestEquityPoint).filter(BacktestEquityPoint.run_id == job_id).all()
            assert run is not None
            assert run.status == "completed"
            assert run.strategy_id == "volume_surge"
            assert run.timeframe == "3m"
            assert run.meta_json["ticker"] == "005930"
            assert run.summary_json["trade_count"] == 1
            assert len(trades) == 1
            assert trades[0].entry_time == base + timedelta(minutes=3)
            assert len(points) == 1
        restored_service = BacktestJobService(session_factory=session_factory, backtest_repo=BacktestRepository())
        restored = await restored_service.get_job(job_id)
        assert restored is not None
        assert restored["status"] == "completed"
        assert restored["persistent"] is True
        result = restored["result"]
        assert isinstance(result, dict)
        assert result["trade_count"] == 1
        restored_list = await restored_service.list_jobs()
        assert restored_list[0]["job_id"] == job_id
        assert await restored_service.count_jobs(status="completed") == 1
        return job_id

    assert asyncio.run(scenario())
