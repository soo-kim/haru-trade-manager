from datetime import datetime

from app.runtime.signal_queue import SignalEvent
from app.strategies.base import Strategy, StrategyContext
from app.strategies.helpers import get_recent_candles, pct_change


class VolumeSurge(Strategy):
    def __init__(self) -> None:
        super().__init__("4", "5m", [("09:00", "15:20"), ("15:30", "20:00")])

    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        candles = get_recent_candles(context.db, context.ticker, context.timeframe, 25)
        if len(candles) < 21:
            return None
        current = candles[-1]
        avg_vol = sum(c.volume for c in candles[-21:-1]) / 20.0
        if avg_vol <= 0:
            return None
        if current.volume < avg_vol * 3:
            return None
        if pct_change(candles[-2].close, current.close) < 1.0:
            return None
        return SignalEvent(
            ticker=context.ticker,
            strategy_id=self.strategy_id,
            timeframe=self.timeframe,
            signal_type="entry",
            side="buy",
            price=current.close,
            signal_time=datetime.now(),
        )
