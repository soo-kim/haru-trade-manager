from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle


class CandleSyncService:
    def upsert_incremental(
        self,
        db: Session,
        ticker: str,
        timeframe: str,
        candle_time: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> Candle:
        existing = db.scalar(
            select(Candle).where(
                Candle.ticker == ticker,
                Candle.timeframe == timeframe,
                Candle.candle_time == candle_time,
            )
        )

        if existing is not None:
            existing.open = open_price
            existing.high = high
            existing.low = low
            existing.close = close
            existing.volume = volume
            db.commit()
            return existing

        candle = Candle(
            ticker=ticker,
            timeframe=timeframe,
            candle_time=candle_time,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
        db.add(candle)
        db.commit()
        return candle
