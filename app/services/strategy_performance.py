from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.repositories.paper import PaperRepository


SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class StrategyMetrics:
    strategy_id: str
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_pnl: float
    expectancy: float
    payoff_ratio: float | None
    profit_factor: float | None


class StrategyPerformanceService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        paper_repo: PaperRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.paper_repo = paper_repo or PaperRepository()

    def report(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        strategy_id: str | None = None,
        strategy_query: str | None = None,
        offset: int = 0,
        limit: int = 100,
        min_trades: int = 0,
        sort_by: str = "total_pnl",
        sort_order: str = "desc",
    ) -> dict[str, object]:
        try:
            with self.session_factory() as db:
                trades = self.paper_repo.list_trades(
                    db,
                    start=start,
                    end=end,
                    strategy_id=strategy_id,
                    limit=100000,
                )
            grouped: dict[str, list] = {}
            for trade in trades:
                if trade.exit_price is None or trade.pnl is None:
                    continue
                grouped.setdefault(trade.strategy_id, []).append(trade)

            metrics = [self._compute(strategy_id, rows) for strategy_id, rows in grouped.items()]
            metrics = [x for x in metrics if x.trades >= max(min_trades, 0)]
            if strategy_query is not None and strategy_query.strip():
                q = strategy_query.strip().lower()
                metrics = [x for x in metrics if q in x.strategy_id.lower()]
            reverse = sort_order.lower() != "asc"
            if sort_by.strip().lower() == "strategy_id":
                metrics.sort(key=lambda x: x.strategy_id, reverse=reverse)
            else:
                metrics.sort(key=lambda x: self._sort_value(x, sort_by), reverse=reverse)

            total = len(metrics)
            safe_offset = max(offset, 0)
            safe_limit = max(limit, 1)
            page = metrics[safe_offset:safe_offset + safe_limit]
            return {
                "ok": True,
                "items": [self._as_dict(x) for x in page],
                "meta": {
                    "total": total,
                    "offset": safe_offset,
                    "limit": safe_limit,
                    "sort_by": sort_by,
                    "sort_order": sort_order.lower(),
                },
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "items": [], "meta": {"total": 0, "offset": offset, "limit": limit}}

    def _compute(self, strategy_id: str, rows: list) -> StrategyMetrics:
        trades = len(rows)
        pnls = [float(x.pnl or 0.0) for x in rows]
        wins = sum(1 for x in pnls if x > 0)
        losses = sum(1 for x in pnls if x < 0)
        total_pnl = sum(pnls)
        avg_pnl = total_pnl / trades if trades else 0.0
        gross_profit = sum(x for x in pnls if x > 0)
        gross_loss_abs = abs(sum(x for x in pnls if x < 0))
        avg_win = (gross_profit / wins) if wins > 0 else 0.0
        avg_loss_abs = (gross_loss_abs / losses) if losses > 0 else 0.0
        payoff_ratio = (avg_win / avg_loss_abs) if avg_loss_abs > 0 else None
        profit_factor = (gross_profit / gross_loss_abs) if gross_loss_abs > 0 else None
        return StrategyMetrics(
            strategy_id=strategy_id,
            trades=trades,
            wins=wins,
            losses=losses,
            win_rate=(wins / trades) if trades else 0.0,
            total_pnl=total_pnl,
            avg_pnl=avg_pnl,
            expectancy=avg_pnl,
            payoff_ratio=payoff_ratio,
            profit_factor=profit_factor,
        )

    @staticmethod
    def _as_dict(item: StrategyMetrics) -> dict[str, object]:
        return {
            "strategy_id": item.strategy_id,
            "trades": item.trades,
            "wins": item.wins,
            "losses": item.losses,
            "win_rate": item.win_rate,
            "total_pnl": item.total_pnl,
            "avg_pnl": item.avg_pnl,
            "expectancy": item.expectancy,
            "payoff_ratio": item.payoff_ratio,
            "profit_factor": item.profit_factor,
        }

    @staticmethod
    def _sort_value(item: StrategyMetrics, sort_by: str) -> float:
        key = sort_by.strip().lower()
        mapping = {
            "strategy_id": 0.0,
            "trades": float(item.trades),
            "wins": float(item.wins),
            "losses": float(item.losses),
            "win_rate": float(item.win_rate),
            "total_pnl": float(item.total_pnl),
            "avg_pnl": float(item.avg_pnl),
            "expectancy": float(item.expectancy),
            "payoff_ratio": float(item.payoff_ratio) if item.payoff_ratio is not None else float("-inf"),
            "profit_factor": float(item.profit_factor) if item.profit_factor is not None else float("-inf"),
        }
        return mapping.get(key, float(item.total_pnl))
