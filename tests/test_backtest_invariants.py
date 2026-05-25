from datetime import datetime, timedelta, timezone

import pytest

from app.backtest.core import BacktestCore
from app.domain.models import Candle, Signal


def test_backtest_entry_uses_n_plus_one_open():
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    candles = [
        Candle(open=100, high=101, low=99, close=100, ts=base),
        Candle(open=120, high=121, low=119, close=120, ts=base + timedelta(minutes=5)),
    ]
    signal = Signal(index=0, side="buy", ticker="005930")
    entry = BacktestCore(slippage_pct=0.05).entry_price_n_plus_one_open(candles, signal)
    assert entry == pytest.approx(120.06)


def test_backtest_raises_when_n_plus_one_missing():
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    candles = [Candle(open=100, high=101, low=99, close=100, ts=base)]
    signal = Signal(index=0, side="buy", ticker="005930")
    with pytest.raises(ValueError):
        BacktestCore().entry_price_n_plus_one_open(candles, signal)
