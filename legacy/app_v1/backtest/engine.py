from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BacktestSignal:
    index: int
    side: str


@dataclass(frozen=True)
class CandleBar:
    open: float
    high: float
    low: float
    close: float


class BacktestEngine:
    def __init__(self, fee_buy_pct: float, fee_sell_pct: float, tax_sell_pct: float, slippage_pct: float) -> None:
        self.fee_buy_pct = fee_buy_pct
        self.fee_sell_pct = fee_sell_pct
        self.tax_sell_pct = tax_sell_pct
        self.slippage_pct = slippage_pct

    def entry_price_n_plus_one_open(self, bars: list[CandleBar], signal: BacktestSignal) -> float:
        next_index = signal.index + 1
        if next_index >= len(bars):
            raise ValueError("N+1 candle is required for backtest entry")

        raw = bars[next_index].open
        if signal.side == "buy":
            return raw * (1 + self.slippage_pct / 100.0)
        return raw * (1 - self.slippage_pct / 100.0)

    def round_trip_cost_pct(self) -> float:
        return self.fee_buy_pct + self.fee_sell_pct + self.tax_sell_pct
