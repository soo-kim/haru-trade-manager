from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol


class AlertSink(Protocol):
    async def send_message(self, text: str) -> bool:
        raise NotImplementedError


class AuditSink(Protocol):
    def log_event(self, *, event_type: str, ip: str, ok: bool, detail: str | None = None) -> bool:
        raise NotImplementedError


@dataclass
class OtpRecord:
    code: str
    expires_at: datetime


@dataclass
class RequestRateState:
    window_start: datetime
    request_count: int
    locked_until: datetime | None = None


@dataclass
class VerifyFailState:
    fail_count: int = 0
    locked_until: datetime | None = None


@dataclass
class SessionRecord:
    session_id: str
    ip: str
    issued_at: datetime
    expires_at: datetime


class OtpAuthService:
    """
    PRD 11.1 기준 OTP 인증 흐름.
    - 4자리 OTP
    - 유효시간 3분
    - IP별 분당 최대 3회 요청, 초과 시 10분 잠금
    - 검증 실패 누적 잠금
    - 세션 쿠키 24시간
    """

    def __init__(
        self,
        *,
        alert_sink: AlertSink | None = None,
        audit_sink: AuditSink | None = None,
        otp_ttl_seconds: int = 180,
        request_window_seconds: int = 60,
        request_limit_per_window: int = 3,
        lock_seconds: int = 600,
        verify_fail_limit: int = 5,
        verify_lock_seconds: int = 600,
        session_ttl_seconds: int = 86400,
    ) -> None:
        self.alert_sink = alert_sink
        self.audit_sink = audit_sink
        self.otp_ttl_seconds = otp_ttl_seconds
        self.request_window_seconds = request_window_seconds
        self.request_limit_per_window = request_limit_per_window
        self.lock_seconds = lock_seconds
        self.verify_fail_limit = verify_fail_limit
        self.verify_lock_seconds = verify_lock_seconds
        self.session_ttl_seconds = session_ttl_seconds
        self._lock = RLock()
        self._otp_by_ip: dict[str, OtpRecord] = {}
        self._rate_by_ip: dict[str, RequestRateState] = {}
        self._verify_by_ip: dict[str, VerifyFailState] = {}
        self._session_by_id: dict[str, SessionRecord] = {}

    async def request_otp(self, *, ip: str) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        with self._lock:
            state = self._rate_by_ip.get(ip)
            if state is None:
                state = RequestRateState(window_start=now, request_count=0)
                self._rate_by_ip[ip] = state

            if state.locked_until is not None and now >= state.locked_until:
                state.locked_until = None
                state.request_count = 0
                state.window_start = now
                self._audit(ip=ip, event_type="otp_request_unlocked", ok=True, detail="lock_expired")

            if state.locked_until is not None and now < state.locked_until:
                left = int((state.locked_until - now).total_seconds())
                self._audit(ip=ip, event_type="otp_request_locked", ok=False, detail=f"retry_after={left}")
                return {"ok": False, "error": "otp_request_locked", "retry_after_seconds": max(left, 1)}
            verify_state = self._verify_by_ip.get(ip)
            if verify_state is not None:
                self._unlock_verify_if_expired(ip=ip, now=now, state=verify_state)
                if verify_state.locked_until is not None and now < verify_state.locked_until:
                    left = int((verify_state.locked_until - now).total_seconds())
                    self._audit(ip=ip, event_type="otp_request_denied_verify_locked", ok=False, detail=f"retry_after={left}")
                    return {"ok": False, "error": "otp_verify_locked", "retry_after_seconds": max(left, 1)}

            if now - state.window_start >= timedelta(seconds=self.request_window_seconds):
                state.window_start = now
                state.request_count = 0
                state.locked_until = None

            state.request_count += 1
            if state.request_count > self.request_limit_per_window:
                state.locked_until = now + timedelta(seconds=self.lock_seconds)
                left = int((state.locked_until - now).total_seconds())
                self._audit(ip=ip, event_type="otp_request_rate_limited", ok=False, detail=f"retry_after={left}")
                return {"ok": False, "error": "otp_request_rate_limited", "retry_after_seconds": max(left, 1)}

            code = self._generate_otp()
            expires_at = now + timedelta(seconds=self.otp_ttl_seconds)
            self._otp_by_ip[ip] = OtpRecord(code=code, expires_at=expires_at)
            self._audit(ip=ip, event_type="otp_request_issued", ok=True, detail=f"expires_at={expires_at.isoformat()}")

        if self.alert_sink is not None:
            await self.alert_sink.send_message(
                f"[OTP] 로그인 코드: {code}"
            )
        payload: dict[str, object] = {
            "ok": True,
            "expires_in_seconds": self.otp_ttl_seconds,
            "requested_at": now.isoformat(),
        }
        return payload

    async def verify_otp(self, *, ip: str, code: str) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        clean_code = code.strip()
        with self._lock:
            verify_state = self._verify_by_ip.get(ip)
            if verify_state is None:
                verify_state = VerifyFailState()
                self._verify_by_ip[ip] = verify_state
            self._unlock_verify_if_expired(ip=ip, now=now, state=verify_state)
            if verify_state.locked_until is not None and now < verify_state.locked_until:
                left = int((verify_state.locked_until - now).total_seconds())
                self._audit(ip=ip, event_type="otp_verify_locked", ok=False, detail=f"retry_after={left}")
                return {"ok": False, "error": "otp_verify_locked", "retry_after_seconds": max(left, 1)}

            otp = self._otp_by_ip.get(ip)
            if otp is None:
                return self._register_verify_failure(ip=ip, now=now, base_error="otp_not_requested")
            if now > otp.expires_at:
                self._otp_by_ip.pop(ip, None)
                return self._register_verify_failure(ip=ip, now=now, base_error="otp_expired")
            if otp.code != clean_code:
                result = self._register_verify_failure(ip=ip, now=now, base_error="otp_mismatch")
            else:
                session_id = secrets.token_hex(24)
                expires_at = now + timedelta(seconds=self.session_ttl_seconds)
                self._session_by_id[session_id] = SessionRecord(
                    session_id=session_id,
                    ip=ip,
                    issued_at=now,
                    expires_at=expires_at,
                )
                self._otp_by_ip.pop(ip, None)
                self._verify_by_ip[ip] = VerifyFailState()
                self._audit(ip=ip, event_type="otp_verify_success", ok=True, detail=f"session={session_id[:8]}")
                result = {
                    "ok": True,
                    "session_id": session_id,
                    "expires_at": expires_at.isoformat(),
                    "expires_in_seconds": self.session_ttl_seconds,
                }

        if not result["ok"] and self.alert_sink is not None:
            await self.alert_sink.send_message(f"[인증 경고] OTP 검증 실패 ip={ip} code={clean_code}")
        return result

    def validate_session(self, *, session_id: str, ip: str) -> dict[str, object]:
        now = datetime.now(timezone.utc)
        with self._lock:
            row = self._session_by_id.get(session_id)
            if row is None:
                self._audit(ip=ip, event_type="session_validate_not_found", ok=False)
                return {"ok": False, "error": "session_not_found"}
            if row.expires_at < now:
                self._session_by_id.pop(session_id, None)
                self._audit(ip=ip, event_type="session_validate_expired", ok=False)
                return {"ok": False, "error": "session_expired"}
            if row.ip != ip:
                self._audit(ip=ip, event_type="session_validate_ip_mismatch", ok=False, detail=f"expected={row.ip}")
                return {"ok": False, "error": "session_ip_mismatch"}
            self._audit(ip=ip, event_type="session_validate_ok", ok=True)
            return {
                "ok": True,
                "session_id": row.session_id,
                "issued_at": row.issued_at.isoformat(),
                "expires_at": row.expires_at.isoformat(),
            }

    def revoke_session(self, session_id: str) -> None:
        with self._lock:
            row = self._session_by_id.pop(session_id, None)
            if row is not None:
                self._audit(ip=row.ip, event_type="session_revoke", ok=True, detail=f"session={session_id[:8]}")

    def _register_verify_failure(self, *, ip: str, now: datetime, base_error: str) -> dict[str, object]:
        state = self._verify_by_ip.get(ip)
        if state is None:
            state = VerifyFailState()
            self._verify_by_ip[ip] = state
        state.fail_count += 1
        if state.fail_count >= self.verify_fail_limit:
            state.locked_until = now + timedelta(seconds=self.verify_lock_seconds)
            left = int((state.locked_until - now).total_seconds())
            self._audit(ip=ip, event_type="otp_verify_locked", ok=False, detail=f"fail_count={state.fail_count}")
            return {
                "ok": False,
                "error": "otp_verify_locked",
                "retry_after_seconds": max(left, 1),
                "fail_count": state.fail_count,
            }
        self._audit(ip=ip, event_type="otp_verify_failed", ok=False, detail=f"{base_error};fail_count={state.fail_count}")
        return {"ok": False, "error": base_error, "fail_count": state.fail_count}

    def _unlock_verify_if_expired(self, *, ip: str, now: datetime, state: VerifyFailState) -> None:
        if state.locked_until is None:
            return
        if now >= state.locked_until:
            state.locked_until = None
            state.fail_count = 0
            self._audit(ip=ip, event_type="otp_verify_unlocked", ok=True, detail="lock_expired")

    def _audit(self, *, ip: str, event_type: str, ok: bool, detail: str | None = None) -> None:
        if self.audit_sink is None:
            return
        try:
            self.audit_sink.log_event(event_type=event_type, ip=ip, ok=ok, detail=detail)
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _generate_otp() -> str:
        return f"{secrets.randbelow(10000):04d}"
