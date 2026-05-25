from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config_manager import ConfigManager
from app.db.models.candle import Candle


class RiskEngine:
    def __init__(self, manager: ConfigManager) -> None:
        self.manager = manager

    def can_open_new_position(self, open_positions: int) -> bool:
        max_positions = int(self.manager.get("max_positions"))
        return open_positions < max_positions

    def atr_period(self) -> int:
        return int(self.manager.get("atr_period"))

    def stop_atr_mult(self) -> float:
        return float(self.manager.get("stop_atr_mult"))

    def tp_atr_mult(self) -> float:
        return float(self.manager.get("tp_atr_mult"))

    def trail_atr_mult(self) -> float:
        return float(self.manager.get("trail_atr_mult"))

    def compute_atr_value(
        self,
        db: Session,
        ticker: str,
        timeframe: str = "5m",
        fallback_price: float = 10000.0,
    ) -> float:
        period = self.atr_period()
        candles = db.scalars(
            select(Candle)
            .where(Candle.ticker == ticker, Candle.timeframe == timeframe)
            .order_by(Candle.candle_time.desc())
            .limit(period)
        ).all()
        if not candles:
            return fallback_price * 0.01

        ranges = [max(c.high - c.low, 0.0) for c in candles]
        atr = sum(ranges) / len(ranges)
        return max(atr, fallback_price * 0.005)
