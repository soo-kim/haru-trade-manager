from __future__ import annotations

from datetime import datetime

from app.domain.models import Candle, Signal
from app.strategies.base import BaseStrategy
from app.strategies.impl.ema_pullback import EmaPullbackStrategy
from app.strategies.impl.gap_momentum import GapMomentumStrategy
from app.strategies.impl.support_resistance import SupportResistanceStrategy
from app.strategies.impl.volatility_breakout import VolatilityBreakoutStrategy
from app.strategies.impl.volume_surge import VolumeSurgeStrategy


class StrategyRegistry:
    def __init__(self, strategies: list[BaseStrategy] | None = None) -> None:
        self._strategies = strategies or [
            GapMomentumStrategy(timeframe="3m"),
            EmaPullbackStrategy(),
            VolatilityBreakoutStrategy(timeframe="3m"),
            VolumeSurgeStrategy(timeframe="3m"),
            SupportResistanceStrategy(),
        ]

    def for_timeframe(self, timeframe: str) -> list[BaseStrategy]:
        return [s for s in self._strategies if s.timeframe == timeframe]

    def scan(
        self,
        *,
        timeframe: str,
        ticker: str,
        candles: list[Candle],
        now: datetime,
    ) -> list[Signal]:
        signals: list[Signal] = []
        for strategy in self.for_timeframe(timeframe):
            signal = strategy.generate(ticker=ticker, candles=candles, now=now)
            if signal is not None:
                signals.append(signal)
        return signals
