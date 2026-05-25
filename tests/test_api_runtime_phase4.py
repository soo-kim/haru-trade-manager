import time

from fastapi.testclient import TestClient

from app.main import app, backtest_service, daily_reporter, safety_manager


def test_test_runtime_disables_external_alert_sink():
    assert safety_manager.alert_sink is None
    assert daily_reporter.alert_sink is None
    assert backtest_service.alert_sink is None


def test_config_and_runtime_endpoints():
    with TestClient(app) as client:
        set_resp = client.post("/config", json={"key": "liquidity_threshold", "value": "77", "changed_by": "test"})
        assert set_resp.status_code == 200
        cfg = client.get("/config")
        assert cfg.status_code == 200
        assert cfg.json()["liquidity_threshold"] == "77"

        pause = client.post("/telegram/command", json={"command": "/pause all"})
        assert pause.status_code == 200
        assert pause.json()["ok"] is True

        runtime = client.get("/system/runtime")
        assert runtime.status_code == 200
        assert runtime.json()["all_paused"] is True
        assert "loop_runtime" in runtime.json()
        assert "cycle_count" in runtime.json()["loop_runtime"]

        resume = client.post("/telegram/command", json={"command": "/resume"})
        assert resume.status_code == 200
        assert resume.json()["ok"] is True


def test_run_cycle_endpoint():
    with TestClient(app) as client:
        resp = client.post("/system/loops/run-cycle")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert "duration_ms" in body


def test_loop_background_and_daily_report_endpoints():
    with TestClient(app) as client:
        started = client.post("/system/loops/start")
        assert started.status_code == 200
        assert started.json()["ok"] is True
        assert "running" in started.json()

        stopped = client.post("/system/loops/stop")
        assert stopped.status_code == 200
        assert stopped.json()["ok"] is True

        report = client.post("/system/reports/daily")
        assert report.status_code == 200
        assert report.json()["ok"] is True
        assert "report" in report.json()

        weekly = client.post("/system/reports/weekly")
        assert weekly.status_code == 200
        assert weekly.json()["ok"] is True
        assert "report" in weekly.json()


def test_live_connectivity_check_endpoint():
    with TestClient(app) as client:
        resp = client.post("/system/live/connectivity-check")
        assert resp.status_code == 200
        body = resp.json()
        assert "ok" in body
        assert "enabled" in body


def test_live_preflight_and_rehearsal_endpoints():
    with TestClient(app) as client:
        preflight = client.post("/system/live/preflight")
        assert preflight.status_code == 200
        pre = preflight.json()
        assert "ok" in pre
        assert "checks" in pre

        rehearsal = client.post("/system/live/rehearsal")
        assert rehearsal.status_code == 200
        reh = rehearsal.json()
        assert "ok" in reh
        assert "cycles" in reh


def test_performance_and_paper_report_endpoints():
    with TestClient(app) as client:
        twr = client.get("/system/performance/twr")
        assert twr.status_code == 200
        assert "ok" in twr.json()

        detect = client.post("/system/performance/cash-flow/detect")
        assert detect.status_code == 200
        assert "ok" in detect.json()

        snapshots = client.get("/system/performance/snapshots")
        assert snapshots.status_code == 200
        assert "ok" in snapshots.json()

        cash_flows = client.get("/system/performance/cash-flows")
        assert cash_flows.status_code == 200
        assert "ok" in cash_flows.json()

        paper = client.get("/paper_report")
        assert paper.status_code == 200
        assert "ok" in paper.json()


def test_backtest_job_endpoints():
    payload = {
        "candles": [
            {"open": 100, "high": 101, "low": 99, "close": 100, "ts": "2026-01-01T09:00:00+00:00", "volume": 10},
            {"open": 101, "high": 103, "low": 100, "close": 102, "ts": "2026-01-01T09:05:00+00:00", "volume": 11},
            {"open": 102, "high": 104, "low": 101, "close": 103, "ts": "2026-01-01T09:10:00+00:00", "volume": 12},
        ],
        "signals": [
            {"index": 0, "side": "buy", "ticker": "005930"},
            {"index": 1, "side": "buy", "ticker": "005930"},
        ],
        "slippage_pct": 0.05,
    }

    with TestClient(app) as client:
        run_resp = client.post("/system/backtest/run", json=payload)
        assert run_resp.status_code == 200
        run_body = run_resp.json()
        assert run_body["ok"] is True
        job_id = run_body["job_id"]

        final = None
        for _ in range(100):
            status = client.get(f"/system/backtest/jobs/{job_id}")
            assert status.status_code == 200
            body = status.json()
            assert body["ok"] is True
            if body["status"] in {"completed", "failed"}:
                final = body
                break
            time.sleep(0.01)

        assert final is not None
        assert final["status"] == "completed"
        assert final["progress"] == 100
        assert final["result"]["trade_count"] == 2

        listed = client.get("/system/backtest/jobs")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert any(item["job_id"] == job_id for item in items)

        listed_filtered = client.get("/system/backtest/jobs?status=completed&limit=1&offset=0")
        assert listed_filtered.status_code == 200
        assert listed_filtered.json()["ok"] is True
        assert "meta" in listed_filtered.json()

        auto_status = client.get("/system/backtest/auto/status")
        assert auto_status.status_code == 200
        assert auto_status.json()["ok"] is True

        auto_run = client.post("/system/backtest/auto/run-now")
        assert auto_run.status_code == 200
        assert auto_run.json()["ok"] is True


def test_universe_endpoints_degraded_safe():
    with TestClient(app) as client:
        listed = client.get("/system/universe")
        assert listed.status_code == 200
        assert "ok" in listed.json()

        upserted = client.post(
            "/system/universe/upsert",
            json={
                "ticker": "005930",
                "name": "Samsung",
                "market": "KOSPI200",
                "in_universe": True,
                "is_active": True,
                "is_blocked": False,
                "status": "normal",
            },
        )
        assert upserted.status_code == 200
        assert "ok" in upserted.json()
