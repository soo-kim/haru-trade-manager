from datetime import datetime

from app.runtime.signal_queue import SignalEvent
from app.strategies.base import Strategy, StrategyContext
from app.strategies.helpers import get_recent_candles


class VolatilityBreakout(Strategy):
    def __init__(self, k: float = 0.5) -> None:
        super().__init__("3", "5m", [("09:00", "15:20")])
        self.k = k

    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        candles = get_recent_candles(context.db, context.ticker, context.timeframe, 80)
        if len(candles) < 50:
            return None
        daily = get_recent_candles(context.db, context.ticker, "1d", 2)
        if len(daily) < 2:
            return None
        prev = daily[-2]
        breakout = prev.high + ((prev.high - prev.low) * self.k)
        current = candles[-1].close
        if current <= breakout:
            return None
        return SignalEvent(
            ticker=context.ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            signal_type="entry",
            side="buy",
            price=current,
            signal_time=datetime.now(),
        )
