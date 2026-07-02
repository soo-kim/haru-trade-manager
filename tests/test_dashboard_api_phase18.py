from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app


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


def test_dashboard_requires_session():
    with TestClient(app) as client:
        resp = client.get("/dashboard/summary")
        assert resp.status_code == 401


def test_dashboard_summary_and_backtests_schema():
    ip = "10.20.30.42"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        _login(client, ip=ip)

        summary = client.get("/dashboard/summary", headers=headers)
        assert summary.status_code == 200
        body = summary.json()
        assert body["ok"] is True
        assert "data" in body
        assert "meta" in body

        backtests = client.get("/dashboard/backtests?page=1&page_size=10", headers=headers)
        assert backtests.status_code == 200
        b = backtests.json()
        assert b["ok"] is True
        assert "items" in b["data"]
        assert "total" in b["meta"]

        universe = client.get("/dashboard/universe?page=1&page_size=10", headers=headers)
        assert universe.status_code == 200
        u = universe.json()
        assert "ok" in u
        assert "items" in u["data"]
        assert "meta" in u

        positions = client.get("/dashboard/positions?page=1&page_size=10", headers=headers)
        assert positions.status_code == 200
        p = positions.json()
        assert "ok" in p
        assert "data" in p

        settings_history = client.get("/dashboard/settings/history?page=1&page_size=10", headers=headers)
        assert settings_history.status_code == 200
        s = settings_history.json()
        assert "ok" in s
        assert "data" in s

        strategy = client.get("/dashboard/strategy-performance?page=1&page_size=10", headers=headers)
        assert strategy.status_code == 200
        sp = strategy.json()
        assert "ok" in sp
        assert "data" in sp

        strategy_filtered = client.get(
            "/dashboard/strategy-performance?page=1&page_size=10&sort_by=win_rate&sort_order=asc&min_trades=0&q=s",
            headers=headers,
        )
        assert strategy_filtered.status_code == 200
        sf = strategy_filtered.json()
        assert "ok" in sf
        assert "meta" in sf

        market_coverage = client.get("/dashboard/market-data/coverage?timeframe=3m", headers=headers)
        assert market_coverage.status_code == 200
        mc = market_coverage.json()
        assert mc["ok"] is True
        assert "universe_count" in mc["data"]
        assert "3m" in mc["data"]["timeframes"]

        collection_states = client.get("/dashboard/market-data/collection-states?timeframe=3m", headers=headers)
        assert collection_states.status_code == 200
        cs = collection_states.json()
        assert cs["ok"] is True
        assert "items" in cs["data"]

        audit = client.get("/dashboard/auth/audit?page=1&page_size=10", headers=headers)
        assert audit.status_code == 200
        au = audit.json()
        assert "ok" in au
        assert "items" in au["data"]
        assert "meta" in au

        metrics = client.get("/dashboard/auth/metrics?last_hours=24", headers=headers)
        assert metrics.status_code == 200
        mt = metrics.json()
        assert "ok" in mt
        assert "data" in mt
        assert "meta" in mt


def test_dashboard_html_pages():
    ip = "10.20.30.43"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        login_page = client.get("/dashboard/login")
        assert login_page.status_code == 200
        assert "대시보드 OTP 로그인" in login_page.text

        redirect_before = client.get("/dashboard/app", headers=headers, follow_redirects=False)
        assert redirect_before.status_code in {302, 307}

        _login(client, ip=ip)
        app_page = client.get("/dashboard/app", headers=headers)
        assert app_page.status_code == 200
        assert "하루 트레이드 대시보드" in app_page.text
        assert "데이터 수집 현황" in app_page.text
        assert "loadMarketDataCoverage" in app_page.text
        assert "/dashboard/market-data/coverage" in app_page.text
