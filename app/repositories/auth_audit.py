from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.auth_audit import AuthAuditLog


class AuthAuditRepository:
    def create(
        self,
        db: Session,
        *,
        event_type: str,
        ip: str,
        ok: bool,
        detail: str | None = None,
    ) -> AuthAuditLog:
        row = AuthAuditLog(event_type=event_type, ip=ip, ok=ok, detail=detail)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        ip: str | None = None,
        ok: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[AuthAuditLog]:
        stmt = select(AuthAuditLog)
        if event_type is not None and event_type.strip():
            stmt = stmt.where(AuthAuditLog.event_type == event_type)
        if ip is not None and ip.strip():
            stmt = stmt.where(AuthAuditLog.ip == ip)
        if ok is not None:
            stmt = stmt.where(AuthAuditLog.ok.is_(ok))
        if start is not None:
            stmt = stmt.where(AuthAuditLog.created_at >= start)
        if end is not None:
            stmt = stmt.where(AuthAuditLog.created_at <= end)
        rows = db.scalars(
            stmt.order_by(AuthAuditLog.created_at.desc()).offset(max(offset, 0)).limit(limit)
        ).all()
        return list(rows)

    def count(
        self,
        db: Session,
        *,
        event_type: str | None = None,
        event_types: list[str] | None = None,
        ip: str | None = None,
        ok: bool | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AuthAuditLog)
        if event_type is not None and event_type.strip():
            stmt = stmt.where(AuthAuditLog.event_type == event_type)
        if event_types:
            normalized = [x for x in event_types if x and x.strip()]
            if normalized:
                stmt = stmt.where(AuthAuditLog.event_type.in_(normalized))
        if ip is not None and ip.strip():
            stmt = stmt.where(AuthAuditLog.ip == ip)
        if ok is not None:
            stmt = stmt.where(AuthAuditLog.ok.is_(ok))
        if start is not None:
            stmt = stmt.where(AuthAuditLog.created_at >= start)
        if end is not None:
            stmt = stmt.where(AuthAuditLog.created_at <= end)
        return int(db.execute(stmt).scalar_one())
