from __future__ import annotations

import math
from datetime import datetime
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.paper import PaperRepository
from app.repositories.performance import PerformanceRepository


SessionFactory = Callable[[], Session]


class PerformanceService:
    """
    Account snapshot + cash-flow based TWR service.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        performance_repo: PerformanceRepository | None = None,
        paper_repo: PaperRepository | None = None,
        auto_cash_flow_min_amount: float = 10_000.0,
    ) -> None:
        self.session_factory = session_factory
        self.performance_repo = performance_repo or PerformanceRepository()
        self.paper_repo = paper_repo or PaperRepository()
        self.auto_cash_flow_min_amount = auto_cash_flow_min_amount

    def record_snapshot(
        self,
        *,
        snapshot_time: datetime,
        snapshot_type: str,
        total_assets: float,
        cash: float,
        stock_value: float,
        margin_used: float = 0.0,
        open_positions: int = 0,
    ) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                row = self.performance_repo.create_snapshot(
                    db,
                    snapshot_time=snapshot_time,
                    snapshot_type=snapshot_type,
                    total_assets=total_assets,
                    cash=cash,
                    stock_value=stock_value,
                    margin_used=margin_used,
                    open_positions=open_positions,
                )
            return {
                "ok": True,
                "id": row.id,
                "snapshot_time": row.snapshot_time.isoformat(),
                "snapshot_type": row.snapshot_type,
                "total_assets": row.total_assets,
                "cash": row.cash,
                "stock_value": row.stock_value,
                "margin_used": row.margin_used,
                "open_positions": row.open_positions,
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc)}

    def record_cash_flow(
        self,
        *,
        flow_time: datetime,
        amount: float,
        total_before: float,
        total_after: float,
        detected_by: str = "manual",
    ) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                row = self.performance_repo.create_cash_flow(
                    db,
                    flow_time=flow_time,
                    amount=amount,
                    total_before=total_before,
                    total_after=total_after,
                    detected_by=detected_by,
                )
            return {
                "ok": True,
                "id": row.id,
                "flow_time": row.flow_time.isoformat(),
                "amount": row.amount,
                "total_before": row.total_before,
                "total_after": row.total_after,
                "detected_by": row.detected_by,
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc)}

    def detect_cash_flows(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        min_amount: float | None = None,
    ) -> dict[str, object]:
        threshold = self.auto_cash_flow_min_amount if min_amount is None else min_amount
        created: list[dict[str, object]] = []
        try:
            with self.session_factory() as db:
                snapshots = self.performance_repo.list_snapshots(db, start=start, end=end)
                if len(snapshots) < 2:
                    return {"ok": True, "created": 0, "items": []}

                for prev, curr in zip(snapshots, snapshots[1:]):
                    pnl = self._sum_realized_pnl(
                        db,
                        start=prev.snapshot_time,
                        end=curr.snapshot_time,
                    )
                    delta_assets = curr.total_assets - prev.total_assets
                    inferred_flow = delta_assets - pnl
                    if abs(inferred_flow) < threshold:
                        continue
                    if self.performance_repo.has_cash_flow_near(db, flow_time=curr.snapshot_time):
                        continue
                    row = self.performance_repo.create_cash_flow(
                        db,
                        flow_time=curr.snapshot_time,
                        amount=inferred_flow,
                        total_before=curr.total_assets - inferred_flow,
                        total_after=curr.total_assets,
                        detected_by="auto",
                    )
                    created.append(
                        {
                            "id": row.id,
                            "flow_time": row.flow_time.isoformat(),
                            "amount": row.amount,
                            "total_before": row.total_before,
                            "total_after": row.total_after,
                            "detected_by": row.detected_by,
                        }
                    )
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "created": 0, "items": []}
        return {"ok": True, "created": len(created), "items": created}

    def list_snapshot_records(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        snapshot_type: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                total = self.performance_repo.count_snapshots(
                    db,
                    start=start,
                    end=end,
                    snapshot_type=snapshot_type,
                )
                rows = self.performance_repo.list_snapshots(
                    db,
                    start=start,
                    end=end,
                    snapshot_type=snapshot_type,
                    offset=offset,
                    limit=limit,
                )
            return {
                "ok": True,
                "meta": {"total": total, "offset": offset, "limit": limit},
                "items": [
                    {
                        "id": x.id,
                        "snapshot_time": x.snapshot_time.isoformat(),
                        "snapshot_type": x.snapshot_type,
                        "total_assets": x.total_assets,
                        "cash": x.cash,
                        "stock_value": x.stock_value,
                        "margin_used": x.margin_used,
                        "open_positions": x.open_positions,
                    }
                    for x in rows
                ],
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "items": []}

    def list_cash_flow_records(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        detected_by: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                total = self.performance_repo.count_cash_flows(
                    db,
                    start=start,
                    end=end,
                    detected_by=detected_by,
                )
                rows = self.performance_repo.list_cash_flows(
                    db,
                    start=start,
                    end=end,
                    detected_by=detected_by,
                    offset=offset,
                    limit=limit,
                )
            return {
                "ok": True,
                "meta": {"total": total, "offset": offset, "limit": limit},
                "items": [
                    {
                        "id": x.id,
                        "flow_time": x.flow_time.isoformat(),
                        "amount": x.amount,
                        "total_before": x.total_before,
                        "total_after": x.total_after,
                        "detected_by": x.detected_by,
                    }
                    for x in rows
                ],
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "items": []}

    def twr_report(self, *, start: datetime | None = None, end: datetime | None = None) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                snapshots = self.performance_repo.list_snapshots(db, start=start, end=end)
                cash_flows = self.performance_repo.list_cash_flows(db, start=start, end=end)
                if len(snapshots) < 2:
                    return {
                        "ok": True,
                        "twr": 0.0,
                        "twr_pct": 0.0,
                        "period_count": max(len(snapshots) - 1, 0),
                        "cash_flow_count": len(cash_flows),
                        "cumulative_pnl": 0.0,
                        "realized_trade_pnl": 0.0,
                        "account_drift": 0.0,
                    }

                twr = self._compute_twr(snapshots=snapshots, cash_flows=cash_flows)
                total_flow = sum(x.amount for x in cash_flows)
                cumulative_pnl = snapshots[-1].total_assets - snapshots[0].total_assets - total_flow
                realized_trade_pnl = self._sum_realized_pnl(
                    db,
                    start=snapshots[0].snapshot_time,
                    end=snapshots[-1].snapshot_time,
                )
                account_drift = cumulative_pnl - realized_trade_pnl
                return {
                    "ok": True,
                    "twr": twr,
                    "twr_pct": twr * 100.0,
                    "period_count": len(snapshots) - 1,
                    "cash_flow_count": len(cash_flows),
                    "cumulative_pnl": cumulative_pnl,
                    "realized_trade_pnl": realized_trade_pnl,
                    "account_drift": account_drift,
                }
        except SQLAlchemyError as exc:
            return {
                "ok": False,
                "error": str(exc),
                "twr": 0.0,
                "twr_pct": 0.0,
                "period_count": 0,
                "cash_flow_count": 0,
                "cumulative_pnl": 0.0,
                "realized_trade_pnl": 0.0,
                "account_drift": 0.0,
            }

    def equity_curve(self, *, start: datetime | None = None, end: datetime | None = None) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                snapshots = self.performance_repo.list_snapshots(db, start=start, end=end)
                cash_flows = self.performance_repo.list_cash_flows(db, start=start, end=end)
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "items": []}

        if not snapshots:
            return {"ok": True, "items": [], "meta": {"count": 0}}

        items: list[dict[str, object]] = []
        cf_idx = 0
        cumulative_flow = 0.0
        baseline_adjusted: float | None = None
        twr_compound = 1.0
        prev = None

        for snap in snapshots:
            while cf_idx < len(cash_flows) and cash_flows[cf_idx].flow_time <= snap.snapshot_time:
                cumulative_flow += cash_flows[cf_idx].amount
                cf_idx += 1

            adjusted_assets = snap.total_assets - cumulative_flow
            if baseline_adjusted is None:
                baseline_adjusted = adjusted_assets
            cumulative_pnl = adjusted_assets - baseline_adjusted

            period_return = 0.0
            if prev is not None and prev.total_assets > 0:
                flow_since_prev = sum(
                    cf.amount for cf in cash_flows if prev.snapshot_time < cf.flow_time <= snap.snapshot_time
                )
                gross = (snap.total_assets - flow_since_prev) / prev.total_assets
                period_return = gross - 1.0
                twr_compound *= max(gross, 0.0)

            items.append(
                {
                    "snapshot_time": snap.snapshot_time.isoformat(),
                    "total_assets": snap.total_assets,
                    "cash": snap.cash,
                    "stock_value": snap.stock_value,
                    "margin_used": snap.margin_used,
                    "open_positions": snap.open_positions,
                    "cumulative_pnl": cumulative_pnl,
                    "period_return": period_return,
                    "twr": twr_compound - 1.0,
                }
            )
            prev = snap

        return {
            "ok": True,
            "items": items,
            "meta": {
                "count": len(items),
                "twr": twr_compound - 1.0,
                "twr_pct": (twr_compound - 1.0) * 100.0,
            },
        }

    def _sum_realized_pnl(self, db: Session, *, start: datetime, end: datetime) -> float:
        trades = self.paper_repo.list_trades(db, start=start, end=end)
        return sum(
            (x.pnl or 0.0)
            for x in trades
            if x.exit_price is not None and x.pnl is not None and start < x.created_at <= end
        )

    @staticmethod
    def _compute_twr(*, snapshots: list, cash_flows: list) -> float:
        compound = 1.0
        for prev, curr in zip(snapshots, snapshots[1:]):
            if prev.total_assets <= 0:
                continue
            flow = sum(
                cf.amount
                for cf in cash_flows
                if prev.snapshot_time < cf.flow_time <= curr.snapshot_time
            )
            gross = (curr.total_assets - flow) / prev.total_assets
            if not math.isfinite(gross):
                continue
            compound *= max(gross, 0.0)
        return compound - 1.0
