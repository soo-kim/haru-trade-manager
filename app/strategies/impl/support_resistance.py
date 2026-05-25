from __future__ import annotations

from datetime import datetime

from app.domain.models import Candle, Signal
from app.strategies.base import BaseStrategy


class SupportResistanceStrategy(BaseStrategy):
    def __init__(self, *, timeframe: str = "15m", active_hours: list[tuple[str, str]] | None = None) -> None:
        super().__init__(
            strategy_id="5",
            timeframe=timeframe,
            active_hours=active_hours or [("09:00", "15:20")],
        )

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if not self.is_active_time(now) or len(candles) < 2:
            return None

        prev = candles[-2]
        last = candles[-1]
        pivot = (prev.high + prev.low + prev.close) / 3
        resistance = (2 * pivot) - prev.low
        support = (2 * pivot) - prev.high

        breakout = last.close >= resistance and last.volume >= prev.volume
        rebound = support > 0 and abs(last.low - support) / support <= 0.003 and last.close > support and last.close >= last.open

        if not (breakout or rebound):
            return None

        return Signal(
            index=len(candles) - 1,
            side="buy",
            ticker=ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            price=last.close,
            signal_time=now,
        )
