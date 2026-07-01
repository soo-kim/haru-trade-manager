from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.db.session import SessionLocal
from app.main import app
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository
from app.repositories.universe import UniverseRepository


def _seed_batch_symbol(ticker: str, *, timeframe: str = "3m") -> tuple[datetime, datetime]:
    base = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc)
    candle_repo = CandleRepository()
    universe_repo = UniverseRepository()
    state_repo = CandleCollectionStateRepository()
    with SessionLocal() as db:
        universe_repo.upsert_symbol(db, ticker=ticker, name=f"테스트{ticker}", market="KOSPI", in_universe=True, is_active=True)
        candles = []
        for idx in range(5):
            ts = base + timedelta(minutes=3 * idx)
            price = 100.0 + idx
            candles.append(
                {
                    "candle_time": ts,
                    "open": price,
                    "high": price + 2,
                    "low": price - 1,
                    "close": price + 1,
                    "volume": 1000 + idx,
                }
            )
        candle_repo.upsert_batch(db, ticker=ticker, timeframe=timeframe, candles=candles)
        state_repo.record_success(
            db,
            ticker=ticker,
            timeframe=timeframe,
            first_candle_time=base,
            last_candle_time=base + timedelta(minutes=12),
            row_count=5,
            source="test",
            collected_at=base + timedelta(minutes=15),
        )
    return base, base + timedelta(minutes=12)


def test_system_batch_backtest_run_and_items_api() -> None:
    start, end = _seed_batch_symbol("TBT001")
    with TestClient(app) as client:
        resp = client.post(
            "/system/backtest/batch/run",
            json={
                "strategy_id": "1",
                "timeframe": "3m",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "universe": {"tickers": ["TBT001"]},
                "params": {"slippage_pct": 0.0},
                "min_candles": 2,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "completed"
        assert body["meta"]["run_type"] == "batch_parent"
        job_id = body["job_id"]

        items = client.get(f"/system/backtest/batch/jobs/{job_id}/items")
        assert items.status_code == 200
        item_body = items.json()
        assert item_body["ok"] is True
        assert item_body["meta"]["total"] == 1
        assert item_body["items"][0]["ticker"] == "TBT001"
        assert item_body["items"][0]["run_type"] == "batch_child"


def test_dashboard_batch_backtest_run_requires_session_and_returns_parent_job() -> None:
    start, end = _seed_batch_symbol("TBT002")
    ip = "10.20.30.88"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        client.post("/auth/otp/request", headers=headers)
        code = main_module.auth_service._otp_by_ip[ip].code  # noqa: SLF001
        login = client.post("/auth/otp/verify", headers=headers, json={"code": code})
        assert login.status_code == 200

        resp = client.post(
            "/dashboard/backtests/batch-run",
            headers=headers,
            json={
                "strategy_id": "1",
                "timeframe": "3m",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "universe": {"tickers": ["TBT002"]},
                "params": {"slippage_pct": 0.0},
                "min_candles": 2,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "completed"
        assert body["meta"]["run_type"] == "batch_parent"
        job_id = body["job_id"]

        items = client.get(f"/dashboard/backtests/{job_id}/items", headers=headers)
        assert items.status_code == 200
        item_body = items.json()
        assert item_body["ok"] is True
        assert item_body["meta"]["total"] == 1
        assert item_body["data"]["items"][0]["ticker"] == "TBT002"
