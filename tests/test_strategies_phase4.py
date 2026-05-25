from datetime import datetime, timezone

from app.domain.models import Candle
from app.strategies.impl.ema_pullback import EmaPullbackStrategy
from app.strategies.impl.gap_momentum import GapMomentumStrategy
from app.strategies.impl.support_resistance import SupportResistanceStrategy
from app.strategies.impl.volatility_breakout import VolatilityBreakoutStrategy
from app.strategies.impl.volume_surge import VolumeSurgeStrategy
from app.strategies.registry import StrategyRegistry


def _candle(price: float, *, volume: float = 1000.0) -> Candle:
    return Candle(open=price, high=price + 1, low=price - 1, close=price, volume=volume, ts=datetime.now(timezone.utc))


def test_gap_momentum_generates_signal_for_large_gap():
    strategy = GapMomentumStrategy(active_hours=[("09:00", "09:30")])
    candles = [_candle(100), Candle(open=103, high=104, low=102, close=103.5, volume=1000, ts=datetime.now(timezone.utc))]
    now = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)
    signal = strategy.generate(ticker="005930", candles=candles, now=now)
    assert signal is not None
    assert signal.strategy_id == "1"


def test_ema_pullback_generates_signal_when_trend_and_pullback_match():
    strategy = EmaPullbackStrategy(active_hours=[("09:00", "15:20")])
    candles = [_candle(100 + i * 0.05, volume=1000 + i * 10) for i in range(60)]
    candles[-1] = Candle(
        open=102.6,
        high=102.9,
        low=102.3,
        close=102.6,
        volume=5000.0,
        ts=datetime.now(timezone.utc),
    )
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    signal = strategy.generate(ticker="005930", candles=candles, now=now)
    assert signal is not None
    assert signal.strategy_id == "2"


def test_volatility_breakout_generates_signal():
    strategy = VolatilityBreakoutStrategy(k=0.5, active_hours=[("09:00", "15:20")])
    prev = Candle(open=100, high=105, low=95, close=100, volume=1000, ts=datetime.now(timezone.utc))
    curr = Candle(open=106, high=111, low=105, close=110, volume=1000, ts=datetime.now(timezone.utc))
    now = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
    signal = strategy.generate(ticker="005930", candles=[prev, curr], now=now)
    assert signal is not None
    assert signal.strategy_id == "3"


def test_volume_surge_generates_signal():
    strategy = VolumeSurgeStrategy(active_hours=[("09:00", "15:20")])
    candles = [_candle(100 + i * 0.1, volume=1000) for i in range(20)]
    candles.append(Candle(open=103, high=105, low=102, close=104.5, volume=4000, ts=datetime.now(timezone.utc)))
    now = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    signal = strategy.generate(ticker="005930", candles=candles, now=now)
    assert signal is not None
    assert signal.strategy_id == "4"


def test_support_resistance_generates_breakout_signal():
    strategy = SupportResistanceStrategy(active_hours=[("09:00", "15:20")])
    prev = Candle(open=100, high=110, low=90, close=100, volume=1000, ts=datetime.now(timezone.utc))
    curr = Candle(open=109, high=115, low=108, close=115, volume=1500, ts=datetime.now(timezone.utc))
    now = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
    signal = strategy.generate(ticker="005930", candles=[prev, curr], now=now)
    assert signal is not None
    assert signal.strategy_id == "5"


def test_strategy_registry_filters_by_timeframe():
    registry = StrategyRegistry()
    three_min = registry.for_timeframe("3m")
    five_min = registry.for_timeframe("5m")
    fifteen_min = registry.for_timeframe("15m")
    assert len(three_min) == 3
    assert len(five_min) == 0
    assert len(fifteen_min) == 2
