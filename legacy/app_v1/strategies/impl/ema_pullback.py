from datetime import datetime

from app.runtime.signal_queue import SignalEvent
from app.strategies.base import Strategy, StrategyContext
from app.strategies.helpers import get_recent_candles


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    k = 2 / (period + 1)
    result = values[0]
    for v in values[1:]:
        result = (v * k) + (result * (1 - k))
    return result


class EmaPullback(Strategy):
    def __init__(self) -> None:
        super().__init__("2", "15m", [("09:00", "15:20")])

    def generate_signal(self, context: StrategyContext) -> SignalEvent | None:
        candles = get_recent_candles(context.db, context.ticker, context.timeframe, 70)
        if len(candles) < 60:
            return None
        closes = [c.close for c in candles]
        ema5 = ema(closes[-20:], 5)
        ema20 = ema(closes[-30:], 20)
        ema60 = ema(closes, 60)
        current = closes[-1]
        if not (ema5 > ema20 > ema60):
            return None
        if current < ema20 * 0.995:
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
