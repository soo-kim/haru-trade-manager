from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle


class PriceProvider:
    def get_last_price(self, db: Session, ticker: str, timeframe: str = "5m") -> float | None:
        last = db.scalar(
            select(Candle)
            .where(Candle.ticker == ticker, Candle.timeframe == timeframe)
            .order_by(Candle.candle_time.desc())
            .limit(1)
        )
        if last is None:
            return None
        return last.close
