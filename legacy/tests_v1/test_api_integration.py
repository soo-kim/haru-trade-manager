import os

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://haru:haru@localhost:6432/haru_trade_test",
)

from app.main import app  # noqa: E402


def test_healthz():
    with TestClient(app) as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_config_update_and_list():
    with TestClient(app) as client:
        set_resp = client.post("/config", json={"key": "max_positions", "value": "12", "changed_by": "test"})
        assert set_resp.status_code == 200
        list_resp = client.get("/config")
        assert list_resp.status_code == 200
        assert list_resp.json()["max_positions"] == "12"


def test_universe_upsert_and_list():
    with TestClient(app) as client:
        upsert = client.post("/universe/upsert", json={"ticker": "005930", "name": "Samsung", "market": "KOSPI"})
        assert upsert.status_code == 200
        listed = client.get("/universe")
        assert listed.status_code == 200
        assert any(x["ticker"] == "005930" for x in listed.json())


def test_telegram_command_without_runtime():
    with TestClient(app) as client:
        resp = client.post("/telegram/command", json={"command": "/status"})
        assert resp.status_code == 400
