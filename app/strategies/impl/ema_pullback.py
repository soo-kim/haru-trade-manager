from __future__ import annotations

from datetime import datetime

from app.domain.models import Candle, Signal
from app.strategies.base import BaseStrategy
from app.strategies.helpers import closes, ema, volumes


class EmaPullbackStrategy(BaseStrategy):
    def __init__(self, *, timeframe: str = "15m", active_hours: list[tuple[str, str]] | None = None) -> None:
        super().__init__(
            strategy_id="2",
            timeframe=timeframe,
            active_hours=active_hours or [("09:00", "15:20")],
        )

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if not self.is_active_time(now) or len(candles) < 60:
            return None

        cls = closes(candles)
        ema5 = ema(cls, 5)
        ema20 = ema(cls, 20)
        ema60 = ema(cls, 60)
        if not (ema5 > ema20 > ema60):
            return None

        last_close = cls[-1]
        pullback_ratio = abs(last_close - ema20) / ema20
        if pullback_ratio > 0.01:
            return None

        vols = volumes(candles)
        if len(vols) >= 20:
            recent_avg = sum(vols[-20:-1]) / 19 if len(vols[-20:-1]) > 0 else 0
            if recent_avg > 0 and vols[-1] < recent_avg:
                return None

        return Signal(
            index=len(candles) - 1,
            side="buy",
            ticker=ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            price=last_close,
            signal_time=now,
        )
