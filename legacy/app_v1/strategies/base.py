from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, time

from sqlalchemy.orm import Session

from app.runtime.signal_queue import SignalEvent


@dataclass(frozen=True)
class StrategyContext:
    ticker: str
    timeframe: str
    now: datetime
    db: Session


class Strategy(ABC):
    strategy_id: str
    timeframe: str
    active_hours: list[tuple[str, str]]

    def __init__(self, strategy_id: str, timeframe: str, active_hours: list[tuple[str, str]]) -> None:
        self.strategy_id = strategy_id
        self.timeframe = timeframe
        self.active_hours = active_hours

    def is_active_now(self, now: datetime) -> bool:
        current = now.time()
        for start, end in self.active_hours:
            start_t = time.fromisoformat(start)
            end_t = time.fromisoformat(end)
            if start_t <= current <= end_t:
                return True
        return False

    @abstractmethod
    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        raise NotImplementedError
