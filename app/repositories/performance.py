from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.performance import AccountSnapshot, CashFlow


class PerformanceRepository:
    def create_snapshot(
        self,
        db: Session,
        *,
        snapshot_time: datetime,
        snapshot_type: str,
        total_assets: float,
        cash: float,
        stock_value: float,
        margin_used: float = 0.0,
        open_positions: int = 0,
    ) -> AccountSnapshot:
        row = AccountSnapshot(
            snapshot_time=snapshot_time,
            snapshot_type=snapshot_type,
            total_assets=total_assets,
            cash=cash,
            stock_value=stock_value,
            margin_used=margin_used,
            open_positions=open_positions,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_snapshots(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        snapshot_type: str | None = None,
        offset: int = 0,
        limit: int = 5000,
    ) -> list[AccountSnapshot]:
        stmt = select(AccountSnapshot).order_by(AccountSnapshot.snapshot_time.asc())
        if start is not None:
            stmt = stmt.where(AccountSnapshot.snapshot_time >= start)
        if end is not None:
            stmt = stmt.where(AccountSnapshot.snapshot_time <= end)
        if snapshot_type is not None and snapshot_type.strip():
            stmt = stmt.where(AccountSnapshot.snapshot_type == snapshot_type)
        return db.scalars(stmt.offset(max(offset, 0)).limit(limit)).all()

    def create_cash_flow(
        self,
        db: Session,
        *,
        flow_time: datetime,
        amount: float,
        total_before: float,
        total_after: float,
        detected_by: str = "auto",
    ) -> CashFlow:
        row = CashFlow(
            flow_time=flow_time,
            amount=amount,
            total_before=total_before,
            total_after=total_after,
            detected_by=detected_by,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_cash_flows(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        detected_by: str | None = None,
        offset: int = 0,
        limit: int = 5000,
    ) -> list[CashFlow]:
        stmt = select(CashFlow).order_by(CashFlow.flow_time.asc())
        if start is not None:
            stmt = stmt.where(CashFlow.flow_time >= start)
        if end is not None:
            stmt = stmt.where(CashFlow.flow_time <= end)
        if detected_by is not None and detected_by.strip():
            stmt = stmt.where(CashFlow.detected_by == detected_by)
        return db.scalars(stmt.offset(max(offset, 0)).limit(limit)).all()

    def has_cash_flow_near(
        self,
        db: Session,
        *,
        flow_time: datetime,
        tolerance_seconds: int = 90,
    ) -> bool:
        begin = flow_time - timedelta(seconds=tolerance_seconds)
        end = flow_time + timedelta(seconds=tolerance_seconds)
        existing = db.scalar(select(CashFlow.id).where(CashFlow.flow_time >= begin, CashFlow.flow_time <= end))
        return existing is not None

    def count_snapshots(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        snapshot_type: str | None = None,
    ) -> int:
        stmt = select(AccountSnapshot.id)
        if start is not None:
            stmt = stmt.where(AccountSnapshot.snapshot_time >= start)
        if end is not None:
            stmt = stmt.where(AccountSnapshot.snapshot_time <= end)
        if snapshot_type is not None and snapshot_type.strip():
            stmt = stmt.where(AccountSnapshot.snapshot_type == snapshot_type)
        return len(db.scalars(stmt).all())

    def count_cash_flows(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        detected_by: str | None = None,
    ) -> int:
        stmt = select(CashFlow.id)
        if start is not None:
            stmt = stmt.where(CashFlow.flow_time >= start)
        if end is not None:
            stmt = stmt.where(CashFlow.flow_time <= end)
        if detected_by is not None and detected_by.strip():
            stmt = stmt.where(CashFlow.detected_by == detected_by)
        return len(db.scalars(stmt).all())
