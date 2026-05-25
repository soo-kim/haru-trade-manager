from datetime import datetime

from app.runtime.signal_queue import SignalEvent
from app.strategies.base import Strategy, StrategyContext


class MockGapMomentum(Strategy):
    def __init__(self) -> None:
        super().__init__(
            strategy_id="gap",
            timeframe="5m",
            active_hours=[("08:00", "08:30"), ("09:00", "09:30")],
        )

    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        if context.now.minute % 10 != 0:
            return None

        return SignalEvent(
            ticker=context.ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            signal_type="entry",
            side="buy",
            price=10000.0,
            signal_time=datetime.now(),
        )
