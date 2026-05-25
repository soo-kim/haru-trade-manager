from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.auth_audit import AuthAuditRepository


SessionFactory = Callable[[], Session]


class AuthAuditService:
    LOCKED_EVENTS = [
        "otp_request_locked",
        "otp_request_rate_limited",
        "otp_request_denied_verify_locked",
        "otp_verify_locked",
    ]
    UNLOCKED_EVENTS = [
        "otp_request_unlocked",
        "otp_verify_unlocked",
    ]

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        repo: AuthAuditRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.repo = repo or AuthAuditRepository()

    def log_event(self, *, event_type: str, ip: str, ok: bool, detail: str | None = None) -> bool:
        try:
            with self.session_factory() as db:
                self.repo.create(db, event_type=event_type, ip=ip, ok=ok, detail=detail)
            return True
        except SQLAlchemyError:
            return False

    def list_events(
        self,
        *,
        event_type: str | None = None,
        ip: str | None = None,
        ok: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                total = self.repo.count(db, event_type=event_type, ip=ip, ok=ok, start=start, end=end)
                rows = self.repo.list(
                    db,
                    event_type=event_type,
                    ip=ip,
                    ok=ok,
                    start=start,
                    end=end,
                    offset=offset,
                    limit=limit,
                )
            return {
                "ok": True,
                "items": [
                    {
                        "id": x.id,
                        "event_type": x.event_type,
                        "ip": x.ip,
                        "ok": x.ok,
                        "detail": x.detail,
                        "created_at": x.created_at.isoformat(),
                    }
                    for x in rows
                ],
                "meta": {"total": total, "offset": offset, "limit": limit},
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "items": [], "meta": {"total": 0, "offset": offset, "limit": limit}}

    def metrics(self, *, last_hours: int = 24, ip: str | None = None) -> dict[str, object]:
        safe_hours = max(last_hours, 1)
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=safe_hours)
        try:
            with self.session_factory() as db:
                total = self.repo.count(db, ip=ip, start=start, end=now)
                failed = self.repo.count(db, ip=ip, ok=False, start=start, end=now)
                locked = self.repo.count(db, ip=ip, event_types=self.LOCKED_EVENTS, start=start, end=now)
                unlocked = self.repo.count(db, ip=ip, event_types=self.UNLOCKED_EVENTS, start=start, end=now)
                successful = self.repo.count(db, ip=ip, ok=True, start=start, end=now)
            failure_rate = (failed / total) if total > 0 else 0.0
            return {
                "ok": True,
                "data": {
                    "total": total,
                    "successful": successful,
                    "failed": failed,
                    "locked": locked,
                    "unlocked": unlocked,
                    "failure_rate": failure_rate,
                },
                "meta": {
                    "last_hours": safe_hours,
                    "start": start.isoformat(),
                    "end": now.isoformat(),
                    "ip": ip,
                },
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "data": {}, "meta": {"last_hours": safe_hours, "ip": ip}}
