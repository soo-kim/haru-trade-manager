from datetime import datetime

from app.runtime.signal_queue import SignalEvent
from app.strategies.base import Strategy, StrategyContext
from app.strategies.helpers import get_recent_candles


class SupportResistance(Strategy):
    def __init__(self) -> None:
        super().__init__("5", "15m", [("09:00", "15:20")])

    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        candles = get_recent_candles(context.db, context.ticker, context.timeframe, 40)
        if len(candles) < 20:
            return None
        recent = candles[-20:]
        resistance = max(c.high for c in recent[:-1])
        support = min(c.low for c in recent[:-1])
        current = recent[-1]
        if current.close > resistance or current.close < support * 1.01:
            return SignalEvent(
                ticker=context.ticker,
                strategy_id=self.strategy_id,
                timeframe=self.timeframe,
                signal_type="entry",
                side="buy",
                price=current.close,
                signal_time=datetime.now(),
            )
        return None
