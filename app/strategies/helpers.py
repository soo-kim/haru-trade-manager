from __future__ import annotations

from app.domain.models import Candle


def ema(values: list[float], period: int) -> float:
    if period <= 0:
        raise ValueError("period must be positive")
    if len(values) < period:
        raise ValueError("not enough samples for EMA")
    k = 2 / (period + 1)
    current = sum(values[:period]) / period
    for value in values[period:]:
        current = (value * k) + (current * (1 - k))
    return current


def closes(candles: list[Candle]) -> list[float]:
    return [c.close for c in candles]


def volumes(candles: list[Candle]) -> list[float]:
    return [c.volume for c in candles]
