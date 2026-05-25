from datetime import datetime

from app.runtime.signal_queue import SignalEvent
from app.strategies.base import Strategy, StrategyContext
from app.strategies.helpers import get_recent_candles, pct_change


class GapMomentum(Strategy):
    def __init__(self) -> None:
        # PRD: 동시호가(08:30~09:00) 제외
        super().__init__("1", "5m", [("08:00", "08:30"), ("09:00", "09:30")])

    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        candles = get_recent_candles(context.db, context.ticker, context.timeframe, 2)
        if len(candles) < 2:
            return None
        prev_close = candles[-2].close
        current_open = candles[-1].open
        if abs(pct_change(prev_close, current_open)) < 2.0:
            return None
        return SignalEvent(
            ticker=context.ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            signal_type="entry",
            side="buy",
            price=candles[-1].close,
            signal_time=datetime.now(),
        )
