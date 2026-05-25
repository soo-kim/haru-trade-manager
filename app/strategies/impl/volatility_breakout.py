from __future__ import annotations

from datetime import datetime

from app.domain.models import Candle, Signal
from app.strategies.base import BaseStrategy


class VolatilityBreakoutStrategy(BaseStrategy):
    def __init__(
        self,
        *,
        timeframe: str = "5m",
        active_hours: list[tuple[str, str]] | None = None,
        k: float = 0.5,
    ) -> None:
        super().__init__(
            strategy_id="3",
            timeframe=timeframe,
            active_hours=active_hours or [("09:00", "15:20")],
        )
        self.k = k

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if not self.is_active_time(now) or len(candles) < 2:
            return None

        prev = candles[-2]
        current = candles[-1]
        target = prev.high + ((prev.high - prev.low) * self.k)
        if current.high < target or current.close < target:
            return None

        return Signal(
            index=len(candles) - 1,
            side="buy",
            ticker=ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            price=current.close,
            signal_time=now,
        )
