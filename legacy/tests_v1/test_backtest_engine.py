import pytest

from app.backtest.engine import BacktestEngine, BacktestSignal, CandleBar


def test_entry_uses_n_plus_one_open_with_slippage():
    engine = BacktestEngine(
        fee_buy_pct=0.015,
        fee_sell_pct=0.015,
        tax_sell_pct=0.18,
        slippage_pct=0.05,
    )
    bars = [
        CandleBar(open=100, high=110, low=95, close=105),
        CandleBar(open=120, high=125, low=119, close=123),
    ]
    signal = BacktestSignal(index=0, side="buy")
    entry = engine.entry_price_n_plus_one_open(bars, signal)
    assert entry == pytest.approx(120.06)


def test_entry_requires_n_plus_one_bar():
    engine = BacktestEngine(0.015, 0.015, 0.18, 0.05)
    bars = [CandleBar(open=100, high=110, low=95, close=105)]
    with pytest.raises(ValueError):
        engine.entry_price_n_plus_one_open(bars, BacktestSignal(index=0, side="buy"))
