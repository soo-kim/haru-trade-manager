from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle
from app.db.models.universe import Symbol


class UniverseService:
    def refresh_active_universe(self, db: Session, liquidity_threshold_eok: float) -> int:
        symbols = db.scalars(select(Symbol).where(Symbol.in_universe.is_(True), Symbol.is_blocked.is_(False))).all()
        changed = 0
        lookback = datetime.now() - timedelta(days=20)
        for symbol in symbols:
            candles = db.scalars(
                select(Candle)
                .where(
                    Candle.ticker == symbol.ticker,
                    Candle.timeframe == "1d",
                    Candle.candle_time >= lookback,
                )
            ).all()
            if not candles:
                continue
            avg_turnover = sum(c.close * c.volume for c in candles) / max(len(candles), 1)
            avg_eok = avg_turnover / 100_000_000.0
            new_active = avg_eok >= liquidity_threshold_eok
            if symbol.is_active != new_active:
                symbol.is_active = new_active
                changed += 1
        db.commit()
        return changed
