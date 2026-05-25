from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, time

from app.domain.models import Candle, Signal


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(hour=int(hh), minute=int(mm))


class BaseStrategy(ABC):
    def __init__(
        self,
        *,
        strategy_id: str,
        timeframe: str,
        active_hours: list[tuple[str, str]],
    ) -> None:
        self.strategy_id = strategy_id
        self.timeframe = timeframe
        self._active_hours = [(_parse_hhmm(start), _parse_hhmm(end)) for start, end in active_hours]

    def is_active_time(self, now: datetime) -> bool:
        current = now.timetz().replace(tzinfo=None)
        for start, end in self._active_hours:
            if start <= current <= end:
                return True
        return False

    @abstractmethod
    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        raise NotImplementedError
