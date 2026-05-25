from __future__ import annotations

from datetime import datetime

from app.domain.models import Candle, Signal
from app.strategies.base import BaseStrategy


class GapMomentumStrategy(BaseStrategy):
    def __init__(self, *, timeframe: str = "5m", active_hours: list[tuple[str, str]] | None = None) -> None:
        super().__init__(
            strategy_id="1",
            timeframe=timeframe,
            active_hours=active_hours or [("08:00", "09:00"), ("09:00", "09:30")],
        )

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if not self.is_active_time(now) or len(candles) < 2:
            return None

        prev_close = candles[-2].close
        opening = candles[-1].open
        if prev_close <= 0:
            return None
        gap_ratio = (opening - prev_close) / prev_close
        if abs(gap_ratio) < 0.02:
            return None

        side = "buy" if gap_ratio > 0 else "sell"
        return Signal(
            index=len(candles) - 1,
            side=side,
            ticker=ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            price=candles[-1].close,
            signal_time=now,
        )
