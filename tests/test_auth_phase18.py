import asyncio
import time

from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.services.auth import OtpAuthService


class CapturingAuditSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def log_event(self, *, event_type: str, ip: str, ok: bool, detail: str | None = None) -> bool:
        self.events.append({"event_type": event_type, "ip": ip, "ok": ok, "detail": detail})
        return True


def _issued_otp_code(ip: str) -> str:
    row = main_module.auth_service._otp_by_ip.get(ip)  # noqa: SLF001
    assert row is not None
    return row.code


def test_auth_otp_request_verify_and_session_flow():
    ip = "10.20.30.40"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        requested = client.post("/auth/otp/request", headers=headers)
        assert requested.status_code == 200
        body = requested.json()
        assert body["ok"] is True
        assert "debug_code" not in body

        verified = client.post("/auth/otp/verify", headers=headers, json={"code": _issued_otp_code(ip)})
        assert verified.status_code == 200
        assert verified.json()["ok"] is True

        session = client.get("/auth/session", headers=headers)
        assert session.status_code == 200
        assert session.json()["ok"] is True

        logout = client.post("/auth/logout", headers=headers)
        assert logout.status_code == 200
        assert logout.json()["ok"] is True

        session_after = client.get("/auth/session", headers=headers)
        assert session_after.status_code == 200
        assert session_after.json()["ok"] is False


def test_auth_otp_request_rate_limit_per_ip():
    ip = "10.20.30.41"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        for _ in range(3):
            resp = client.post("/auth/otp/request", headers=headers)
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

        fourth = client.post("/auth/otp/request", headers=headers)
        assert fourth.status_code == 200
        body = fourth.json()
        assert body["ok"] is False
        assert body["error"] in {"otp_request_rate_limited", "otp_request_locked"}


def test_auth_otp_verify_failure_accumulated_lock():
    ip = "10.20.30.44"
    headers = {"x-forwarded-for": ip}
    with TestClient(app) as client:
        requested = client.post("/auth/otp/request", headers=headers)
        assert requested.status_code == 200
        assert requested.json()["ok"] is True

        locked = None
        for _ in range(5):
            res = client.post("/auth/otp/verify", headers=headers, json={"code": "9999"})
            assert res.status_code == 200
            body = res.json()
            if body["error"] == "otp_verify_locked":
                locked = body
                break
        assert locked is not None
        assert locked["ok"] is False
        assert locked["retry_after_seconds"] > 0
        assert locked["fail_count"] >= 1

        request_after_lock = client.post("/auth/otp/request", headers=headers)
        assert request_after_lock.status_code == 200
        assert request_after_lock.json()["ok"] is False
        assert request_after_lock.json()["error"] == "otp_verify_locked"


def test_auth_audit_logs_request_lock_and_unlock():
    sink = CapturingAuditSink()
    service = OtpAuthService(
        audit_sink=sink,
        request_limit_per_window=1,
        request_window_seconds=60,
        lock_seconds=1,
    )
    ip = "203.0.113.1"
    first = asyncio.run(service.request_otp(ip=ip))
    assert first["ok"] is True

    limited = asyncio.run(service.request_otp(ip=ip))
    assert limited["ok"] is False
    assert limited["error"] in {"otp_request_rate_limited", "otp_request_locked"}

    time.sleep(1.05)
    retry = asyncio.run(service.request_otp(ip=ip))
    assert retry["ok"] is True

    event_types = [x["event_type"] for x in sink.events]
    assert "otp_request_rate_limited" in event_types
    assert "otp_request_unlocked" in event_types


def test_auth_audit_logs_verify_failure_lock_and_unlock():
    sink = CapturingAuditSink()
    service = OtpAuthService(
        audit_sink=sink,
        verify_fail_limit=2,
        verify_lock_seconds=1,
    )
    ip = "203.0.113.2"
    requested = asyncio.run(service.request_otp(ip=ip))
    assert requested["ok"] is True

    first_fail = asyncio.run(service.verify_otp(ip=ip, code="9999"))
    assert first_fail["ok"] is False
    assert first_fail["error"] in {"otp_mismatch", "otp_verify_locked"}

    second_fail = asyncio.run(service.verify_otp(ip=ip, code="9999"))
    assert second_fail["ok"] is False
    assert second_fail["error"] == "otp_verify_locked"

    time.sleep(1.05)
    reopened = asyncio.run(service.request_otp(ip=ip))
    assert reopened["ok"] is True

    event_types = [x["event_type"] for x in sink.events]
    assert "otp_verify_failed" in event_types
    assert "otp_verify_locked" in event_types
    assert "otp_verify_unlocked" in event_types
