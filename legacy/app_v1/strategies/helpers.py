from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle


def get_recent_candles(db: Session, ticker: str, timeframe: str, limit: int) -> list[Candle]:
    rows = db.scalars(
        select(Candle)
        .where(Candle.ticker == ticker, Candle.timeframe == timeframe)
        .order_by(Candle.candle_time.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))


def pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return ((b - a) / a) * 100.0
