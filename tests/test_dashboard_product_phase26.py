from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.db.session import SessionLocal
from app.main import app
from app.repositories.candle import CandleRepository


def _issued_otp_code(ip: str) -> str:
    row = main_module.auth_service._otp_by_ip.get(ip)  # noqa: SLF001
    assert row is not None
    return row.code


def _login(client: TestClient, *, ip: str) -> None:
    headers = {"x-forwarded-for": ip}
    requested = client.post("/auth/otp/request", headers=headers)
    assert requested.status_code == 200
    body = requested.json()
    assert body["ok"] is True
    assert "debug_code" not in body
    code = _issued_otp_code(ip)
    verified = client.post("/auth/otp/verify", headers=headers, json={"code": code})
    assert verified.status_code == 200
    assert verified.json()["ok"] is True


def test_dashboard_product_endpoints():
    ip = "10.20.30.55"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        _login(client, ip=ip)

        settings = client.get("/dashboard/settings", headers=headers)
        assert settings.status_code == 200
        assert settings.json()["ok"] is True
        setting_items = settings.json()["data"]["items"]
        assert setting_items
        assert "label" in setting_items[0]
        assert "description" in setting_items[0]

        set_ok = client.post(
            "/dashboard/settings",
            headers=headers,
            json={"key": "risk_per_trade_pct", "value": "0.6"},
        )
        assert set_ok.status_code == 200
        assert set_ok.json()["ok"] is True

        equity = client.get("/dashboard/performance/equity-curve", headers=headers)
        assert equity.status_code == 200
        assert "ok" in equity.json()
        assert "data" in equity.json()

        trades = client.get("/dashboard/trades?page=1&page_size=10", headers=headers)
        assert trades.status_code == 200
        assert "ok" in trades.json()
        assert "data" in trades.json()

        csv_resp = client.get("/dashboard/trades/export.csv", headers=headers)
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.headers.get("content-type", "")
        assert "id,ticker,strategy_id" in csv_resp.text

        rebalance = client.post(
            "/dashboard/universe/rebalance",
            headers=headers,
            json={"tickers": ["005930", "000660"]},
        )
        assert rebalance.status_code == 200
        assert rebalance.json()["ok"] is True

        universe = client.get("/dashboard/universe?page=1&page_size=10", headers=headers)
        assert universe.status_code == 200
        assert universe.json()["ok"] is True
        for row in universe.json()["data"]["items"]:
            assert "status_label_ko" in row


def test_dashboard_manual_backtest_run():
    ip = "10.20.30.56"
    headers = {"x-forwarded-for": ip}
    repo = CandleRepository()
    base = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for idx in range(40):
            ts = base + timedelta(minutes=5 * idx)
            open_price = 100.0 + (idx * 0.1)
            close_price = open_price + 0.3
            repo.upsert_incremental(
                db,
                ticker="005930",
                timeframe="5m",
                candle_time=ts,
                open_price=open_price,
                high=close_price + 0.2,
                low=open_price - 0.2,
                close=close_price,
                volume=1000 + idx,
            )

    with TestClient(app) as client:
        _login(client, ip=ip)
        payload = {
            "ticker": "005930",
            "strategy_id": "3",
            "timeframe": "5m",
            "start": base.isoformat(),
            "end": (base + timedelta(minutes=5 * 39)).isoformat(),
            "slippage_pct": 0.05,
            "k": 0.5,
        }
        resp = client.post("/dashboard/backtests/manual-run", headers=headers, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "queued"
        assert body["job_id"]


def test_dashboard_manual_backtest_run_three_minute_timeframe():
    ip = "10.20.30.58"
    headers = {"x-forwarded-for": ip}
    repo = CandleRepository()
    base = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for idx in range(40):
            ts = base + timedelta(minutes=3 * idx)
            open_price = 200.0 + (idx * 0.1)
            close_price = open_price + 0.2
            repo.upsert_incremental(
                db,
                ticker="005930",
                timeframe="3m",
                candle_time=ts,
                open_price=open_price,
                high=close_price + 0.1,
                low=open_price - 0.1,
                close=close_price,
                volume=1500 + idx,
            )

    with TestClient(app) as client:
        _login(client, ip=ip)
        payload = {
            "ticker": "005930",
            "strategy_id": "1",
            "timeframe": "3m",
            "start": base.isoformat(),
            "end": (base + timedelta(minutes=3 * 39)).isoformat(),
            "slippage_pct": 0.05,
            "k": 0.5,
        }
        resp = client.post("/dashboard/backtests/manual-run", headers=headers, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["status"] == "queued"
        assert body["job_id"]


def test_dashboard_backtest_candle_range_three_minute_timeframe():
    ip = "10.20.30.59"
    headers = {"x-forwarded-for": ip}
    repo = CandleRepository()
    base = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
    with SessionLocal() as db:
        for idx in range(10):
            ts = base + timedelta(minutes=3 * idx)
            open_price = 300.0 + (idx * 0.2)
            close_price = open_price + 0.1
            repo.upsert_incremental(
                db,
                ticker="005930",
                timeframe="3m",
                candle_time=ts,
                open_price=open_price,
                high=close_price + 0.1,
                low=open_price - 0.1,
                close=close_price,
                volume=2000 + idx,
            )

    with TestClient(app) as client:
        _login(client, ip=ip)
        resp = client.get("/dashboard/backtests/candle-range?ticker=005930&timeframe=3m", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["data"]["ticker"] == "005930"
        assert body["data"]["timeframe"] == "3m"
        assert body["data"]["count"] >= 10
        assert body["data"]["start"] is not None
        assert body["data"]["end"] is not None


def test_dashboard_backtest_candle_range_rejects_unsupported_timeframe():
    ip = "10.20.30.60"
    headers = {"x-forwarded-for": ip}

    with TestClient(app) as client:
        _login(client, ip=ip)
        resp = client.get("/dashboard/backtests/candle-range?ticker=005930&timeframe=2m", headers=headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert "unsupported timeframe" in body["error"]


def test_dashboard_rebalance_uses_prd_seed_when_tickers_empty():
    ip = "10.20.30.57"
    headers = {"x-forwarded-for": ip}

    def _fake_seed() -> dict[str, object]:
        return {
            "ok": True,
            "items": [
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI200"},
                {"ticker": "035420", "name": "NAVER", "market": "KOSPI200"},
            ],
        }

    original = main_module._fetch_prd_initial_universe_seed
    main_module._fetch_prd_initial_universe_seed = _fake_seed
    try:
        with TestClient(app) as client:
            _login(client, ip=ip)
            rebalance = client.post(
                "/dashboard/universe/rebalance",
                headers=headers,
                json={"tickers": None},
            )
            assert rebalance.status_code == 200
            body = rebalance.json()
            assert body["ok"] is True
            assert body["summary"]["source"] == "prd_index_constituents"
            assert body["summary"]["target_count"] == 2
    finally:
        main_module._fetch_prd_initial_universe_seed = original
