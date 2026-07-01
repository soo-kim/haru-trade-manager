from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models.backtest import BacktestEquityPoint, BacktestRun, BacktestTrade


class BacktestRepository:
    def create_run(
        self,
        db: Session,
        *,
        run_id: str,
        name: str | None,
        strategy_id: str,
        timeframe: str,
        start_at: datetime | None,
        end_at: datetime | None,
        params: dict[str, Any] | None,
        slippage_pct: float,
        commission_pct: float,
        status: str,
        meta: dict[str, Any] | None,
        created_at: datetime,
        run_type: str = "single",
        parent_run_id: str | None = None,
        ticker: str | None = None,
    ) -> BacktestRun:
        existing = db.get(BacktestRun, run_id)
        if existing is not None:
            return existing
        row = BacktestRun(
            id=run_id,
            name=name,
            strategy_id=strategy_id,
            timeframe=timeframe,
            start_at=start_at,
            end_at=end_at,
            params_json=dict(params or {}),
            slippage_pct=slippage_pct,
            commission_pct=commission_pct,
            status=status,
            run_type=run_type,
            parent_run_id=parent_run_id,
            ticker=ticker,
            meta_json=dict(meta or {}),
            created_at=created_at,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def mark_running(self, db: Session, *, run_id: str) -> None:
        row = db.get(BacktestRun, run_id)
        if row is None:
            return
        row.status = "running"
        db.commit()

    def mark_completed(
        self,
        db: Session,
        *,
        run_id: str,
        summary: dict[str, Any],
        completed_at: datetime,
        trades: list[dict[str, Any]],
        equity_points: list[dict[str, Any]],
        status: str = "completed",
    ) -> BacktestRun | None:
        row = db.get(BacktestRun, run_id)
        if row is None:
            return None
        db.execute(delete(BacktestTrade).where(BacktestTrade.run_id == run_id))
        db.execute(delete(BacktestEquityPoint).where(BacktestEquityPoint.run_id == run_id))
        row.status = status
        row.summary_json = dict(summary)
        row.error = None
        row.completed_at = completed_at
        for item in trades:
            db.add(BacktestTrade(run_id=run_id, **item))
        for item in equity_points:
            db.add(BacktestEquityPoint(run_id=run_id, **item))
        db.commit()
        db.refresh(row)
        return row

    def mark_failed(self, db: Session, *, run_id: str, error: str, completed_at: datetime) -> BacktestRun | None:
        row = db.get(BacktestRun, run_id)
        if row is None:
            return None
        row.status = "failed"
        row.error = error
        row.completed_at = completed_at
        db.commit()
        db.refresh(row)
        return row

    def list_runs(
        self,
        db: Session,
        *,
        status: str | None = None,
        offset: int = 0,
        limit: int = 50,
        run_type: str | None = None,
        parent_run_id: str | None = None,
    ) -> list[BacktestRun]:
        stmt = select(BacktestRun).order_by(BacktestRun.created_at.desc())
        if status is not None and status.strip():
            stmt = stmt.where(BacktestRun.status == status)
        if run_type is not None and run_type.strip():
            stmt = stmt.where(BacktestRun.run_type == run_type)
        if parent_run_id is not None and parent_run_id.strip():
            stmt = stmt.where(BacktestRun.parent_run_id == parent_run_id)
        return list(db.scalars(stmt.offset(max(offset, 0)).limit(max(limit, 1))).all())

    def list_child_runs(self, db: Session, *, parent_run_id: str) -> list[BacktestRun]:
        stmt = (
            select(BacktestRun)
            .where(BacktestRun.parent_run_id == parent_run_id)
            .order_by(BacktestRun.ticker.asc(), BacktestRun.created_at.asc())
        )
        return list(db.scalars(stmt).all())

    def get_run(self, db: Session, *, run_id: str) -> BacktestRun | None:
        return db.get(BacktestRun, run_id)

    def count_runs(
        self,
        db: Session,
        *,
        status: str | None = None,
        run_type: str | None = None,
        parent_run_id: str | None = None,
    ) -> int:
        stmt = select(func.count(BacktestRun.id))
        if status is not None and status.strip():
            stmt = stmt.where(BacktestRun.status == status)
        if run_type is not None and run_type.strip():
            stmt = stmt.where(BacktestRun.run_type == run_type)
        if parent_run_id is not None and parent_run_id.strip():
            stmt = stmt.where(BacktestRun.parent_run_id == parent_run_id)
        return int(db.scalar(stmt) or 0)
