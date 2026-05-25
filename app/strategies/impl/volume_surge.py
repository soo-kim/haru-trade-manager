from __future__ import annotations

from datetime import datetime

from app.domain.models import Candle, Signal
from app.strategies.base import BaseStrategy
from app.strategies.helpers import volumes


class VolumeSurgeStrategy(BaseStrategy):
    def __init__(self, *, timeframe: str = "5m", active_hours: list[tuple[str, str]] | None = None) -> None:
        super().__init__(
            strategy_id="4",
            timeframe=timeframe,
            active_hours=active_hours or [("09:00", "15:20"), ("15:30", "20:00")],
        )

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if not self.is_active_time(now) or len(candles) < 21:
            return None

        prev = candles[-2]
        last = candles[-1]
        recent = volumes(candles)[-21:-1]
        avg20 = sum(recent) / len(recent) if recent else 0.0
        if avg20 <= 0:
            return None

        if last.volume < (avg20 * 3):
            return None
        if prev.close <= 0:
            return None
        if (last.close - prev.close) / prev.close < 0.01:
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
