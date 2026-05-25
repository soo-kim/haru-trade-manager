from __future__ import annotations

from app.domain.models import Candle, Signal


class BacktestCore:
    def __init__(self, slippage_pct: float = 0.05) -> None:
        self.slippage_pct = slippage_pct

    def entry_price_n_plus_one_open(self, candles: list[Candle], signal: Signal) -> float:
        next_idx = signal.index + 1
        if next_idx >= len(candles):
            raise ValueError("N+1 candle required")
        raw = candles[next_idx].open
        if signal.side == "buy":
            return raw * (1 + self.slippage_pct / 100.0)
        return raw * (1 - self.slippage_pct / 100.0)
