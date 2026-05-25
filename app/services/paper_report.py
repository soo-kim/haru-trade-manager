from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models.paper import PaperTrade
from app.db.session import SessionLocal
from app.repositories.paper import PaperRepository
from app.services.runtime_safety import RuntimeSafetyManager


SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class PaperPassCriteria:
    min_signals: int = 100
    min_days: int = 14
    min_win_rate: float = 0.52
    min_sharpe: float = 1.0
    max_mdd: float = 0.15
    max_position_mismatch: int = 0
    max_error_rate: float = 0.001


class PaperReportService:
    """
    PRD-based paper trading pass/fail report generator.
    """

    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        paper_repo: PaperRepository | None = None,
        runtime_health_provider: Callable[[], dict[str, object]] | None = None,
        safety_manager: RuntimeSafetyManager | None = None,
        criteria: PaperPassCriteria | None = None,
        initial_capital: float = 10_000_000.0,
    ) -> None:
        self.session_factory = session_factory
        self.paper_repo = paper_repo or PaperRepository()
        self.runtime_health_provider = runtime_health_provider
        self.safety_manager = safety_manager
        self.criteria = criteria or PaperPassCriteria()
        self.initial_capital = initial_capital

    def build_report(self) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                trades = self.paper_repo.list_trades(db)
                closed = [t for t in trades if t.exit_price is not None and t.pnl is not None]
                metrics = self._compute_metrics(trades=trades, closed=closed)
                checks = self._check_criteria(metrics)
                passed = all(item["pass"] for item in checks)
                return {
                    "ok": True,
                    "passed": passed,
                    "metrics": metrics,
                    "criteria": checks,
                }
        except SQLAlchemyError as exc:
            return {"ok": False, "passed": False, "error": str(exc), "metrics": {}, "criteria": []}

    def _compute_metrics(self, *, trades: list[PaperTrade], closed: list[PaperTrade]) -> dict[str, float | int]:
        total_signals = len(trades)
        closed_count = len(closed)
        wins = sum(1 for t in closed if (t.pnl or 0.0) > 0)
        win_rate = (wins / closed_count) if closed_count else 0.0
        total_pnl = sum((t.pnl or 0.0) for t in closed)
        expected_value = (total_pnl / closed_count) if closed_count else 0.0

        returns = []
        for t in closed:
            base = t.entry_price * t.quantity
            if base <= 0:
                continue
            returns.append((t.pnl or 0.0) / base)
        sharpe = self._sharpe_ratio(returns)
        mdd = self._max_drawdown(closed)

        if trades:
            first = min(t.created_at for t in trades)
            last = max(t.created_at for t in trades)
            operating_days = (last.date() - first.date()).days + 1
        else:
            operating_days = 0

        position_mismatch_count = 0
        if self.safety_manager is not None:
            position_mismatch_count = sum(1 for e in self.safety_manager.latest_events(limit=1000) if e.code == "position_mismatch")

        error_rate = 0.0
        if self.runtime_health_provider is not None:
            health = self.runtime_health_provider()
            cycle_count = int(health.get("cycle_count") or 0)
            error_count = int(health.get("error_count") or 0)
            error_rate = (error_count / cycle_count) if cycle_count > 0 else 0.0

        return {
            "total_signals": total_signals,
            "operating_days": operating_days,
            "closed_trades": closed_count,
            "win_rate": win_rate,
            "sharpe_ratio": sharpe,
            "mdd": mdd,
            "expected_value": expected_value,
            "total_pnl": total_pnl,
            "position_mismatch_count": position_mismatch_count,
            "error_rate": error_rate,
        }

    @staticmethod
    def _sharpe_ratio(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        avg = mean(returns)
        std = pstdev(returns)
        if std == 0:
            return 10.0 if avg > 0 else 0.0
        return avg / std * math.sqrt(len(returns))

    def _max_drawdown(self, closed: list[PaperTrade]) -> float:
        if not closed:
            return 0.0
        trades = sorted(closed, key=lambda x: x.created_at)
        equity = self.initial_capital
        peak = self.initial_capital
        max_dd = 0.0
        for trade in trades:
            equity += trade.pnl or 0.0
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
        return max_dd

    def _check_criteria(self, metrics: dict[str, float | int]) -> list[dict[str, object]]:
        c = self.criteria
        return [
            self._criterion(
                key="min_signals",
                passed=int(metrics["total_signals"]) >= c.min_signals,
                value=metrics["total_signals"],
                threshold=f">={c.min_signals}",
            ),
            self._criterion(
                key="min_operating_days",
                passed=int(metrics["operating_days"]) >= c.min_days,
                value=metrics["operating_days"],
                threshold=f">={c.min_days}",
            ),
            self._criterion(
                key="win_rate",
                passed=float(metrics["win_rate"]) >= c.min_win_rate,
                value=metrics["win_rate"],
                threshold=f">={c.min_win_rate}",
            ),
            self._criterion(
                key="sharpe_ratio",
                passed=float(metrics["sharpe_ratio"]) >= c.min_sharpe,
                value=metrics["sharpe_ratio"],
                threshold=f">={c.min_sharpe}",
            ),
            self._criterion(
                key="mdd",
                passed=float(metrics["mdd"]) <= c.max_mdd,
                value=metrics["mdd"],
                threshold=f"<={c.max_mdd}",
            ),
            self._criterion(
                key="position_mismatch_count",
                passed=int(metrics["position_mismatch_count"]) <= c.max_position_mismatch,
                value=metrics["position_mismatch_count"],
                threshold=f"<={c.max_position_mismatch}",
            ),
            self._criterion(
                key="error_rate",
                passed=float(metrics["error_rate"]) < c.max_error_rate,
                value=metrics["error_rate"],
                threshold=f"<{c.max_error_rate}",
            ),
        ]

    @staticmethod
    def _criterion(*, key: str, passed: bool, value: float | int, threshold: str) -> dict[str, object]:
        return {
            "key": key,
            "pass": passed,
            "value": value,
            "threshold": threshold,
        }
