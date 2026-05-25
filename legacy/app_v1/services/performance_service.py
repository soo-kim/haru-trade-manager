from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.paper import PaperTrade


class PerformanceService:
    def paper_report(self, db: Session) -> dict:
        trades = db.scalars(select(PaperTrade)).all()
        closed = [t for t in trades if t.exit_price is not None and t.pnl is not None]
        wins = [t for t in closed if (t.pnl or 0.0) > 0]
        win_rate = (len(wins) / len(closed) * 100.0) if closed else 0.0
        return {
            "total_trades": len(trades),
            "closed_trades": len(closed),
            "win_rate_pct": win_rate,
            "meets_min_signals_100": len(trades) >= 100,
        }
