from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PositionExposure:
    position_id: int
    strategy_id: str
    market_value: float


class RiskEngine:
    def can_open_new_position(self, *, open_count: int, max_positions: int) -> bool:
        return open_count < max_positions

    def hit_daily_loss_limit(self, *, daily_loss_pct: float, daily_loss_limit_pct: float) -> bool:
        return daily_loss_pct >= daily_loss_limit_pct

    def hit_stop_count_limit(self, *, stop_count: int, stop_count_limit: int) -> bool:
        return stop_count >= stop_count_limit

    def compute_atr(self, highs: list[float], lows: list[float], closes: list[float]) -> float:
        if not highs or not lows or not closes:
            raise ValueError("high/low/close series are required")
        n = min(len(highs), len(lows), len(closes))
        trs: list[float] = []
        for i in range(n):
            high = highs[i]
            low = lows[i]
            prev_close = closes[i - 1] if i > 0 else closes[i]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)
        return sum(trs) / len(trs)

    def build_stop_take_profit(
        self,
        *,
        entry_price: float,
        atr_value: float,
        stop_atr_mult: float,
        tp_atr_mult: float,
    ) -> tuple[float, float]:
        stop = max(entry_price - (atr_value * stop_atr_mult), 0.0)
        tp = entry_price + (atr_value * tp_atr_mult)
        return stop, tp

    def margin_forced_close_order(
        self,
        *,
        exposures: list[PositionExposure],
        daily_base_capital: float,
        priority: list[str],
    ) -> list[int]:
        total = sum(x.market_value for x in exposures)
        if total <= daily_base_capital:
            return []

        ordered = sorted(
            exposures,
            key=lambda x: priority.index(x.strategy_id) if x.strategy_id in priority else len(priority),
        )
        to_close: list[int] = []
        running = total
        for row in ordered:
            to_close.append(row.position_id)
            running -= row.market_value
            if running <= daily_base_capital:
                break
        return to_close
