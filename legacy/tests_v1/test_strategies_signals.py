from datetime import datetime, timedelta, timezone

from app.db.models.candle import Candle
from app.strategies.base import StrategyContext
from app.strategies.impl.ema_pullback import EmaPullback
from app.strategies.impl.gap_momentum import GapMomentum
from app.strategies.impl.support_resistance import SupportResistance
from app.strategies.impl.volatility_breakout import VolatilityBreakout
from app.strategies.impl.volume_surge import VolumeSurge
from tests.utils import build_session


def add_candle(db, ticker, timeframe, t, o, h, l, c, v):  # noqa: ANN001
    db.add(
        Candle(
            ticker=ticker,
            timeframe=timeframe,
            candle_time=t,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
        )
    )


def test_gap_momentum_signal():
    with build_session() as db:
        t0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        add_candle(db, "AAA", "5m", t0, 100, 101, 99, 100, 1000)
        add_candle(db, "AAA", "5m", t0 + timedelta(minutes=5), 103, 104, 102, 103, 1200)
        db.commit()
        strategy = GapMomentum()
        ctx = StrategyContext(ticker="AAA", timeframe="5m", now=t0 + timedelta(minutes=5), db=db)
        assert strategy.generate_signal(ctx) is not None


def test_ema_pullback_signal():
    with build_session() as db:
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        price = 100.0
        for i in range(70):
            price += 0.3
            add_candle(db, "BBB", "15m", base + timedelta(minutes=15 * i), price - 0.2, price + 0.3, price - 0.5, price, 2000)
        db.commit()
        strategy = EmaPullback()
        ctx = StrategyContext(ticker="BBB", timeframe="15m", now=base + timedelta(minutes=15 * 69), db=db)
        assert strategy.generate_signal(ctx) is not None


def test_volatility_breakout_signal():
    with build_session() as db:
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        for i in range(60):
            p = 100 + (i * 0.2)
            add_candle(db, "CCC", "5m", base + timedelta(minutes=5 * i), p, p + 1, p - 1, p, 1000)
        add_candle(db, "CCC", "1d", base - timedelta(days=2), 95, 100, 90, 96, 1000000)
        add_candle(db, "CCC", "1d", base - timedelta(days=1), 98, 110, 90, 100, 1000000)
        # 마지막 5m 봉을 돌파가로 올림
        add_candle(db, "CCC", "5m", base + timedelta(minutes=5 * 60), 121, 122, 120, 121, 1500)
        db.commit()
        strategy = VolatilityBreakout(k=0.5)
        ctx = StrategyContext(ticker="CCC", timeframe="5m", now=base + timedelta(minutes=5 * 60), db=db)
        assert strategy.generate_signal(ctx) is not None


def test_volume_surge_signal():
    with build_session() as db:
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        price = 100.0
        for i in range(24):
            add_candle(db, "DDD", "5m", base + timedelta(minutes=5 * i), price, price + 0.5, price - 0.5, price, 1000)
            price += 0.1
        add_candle(db, "DDD", "5m", base + timedelta(minutes=5 * 24), 104, 106, 103, 106, 4000)
        db.commit()
        strategy = VolumeSurge()
        ctx = StrategyContext(ticker="DDD", timeframe="5m", now=base + timedelta(minutes=5 * 24), db=db)
        assert strategy.generate_signal(ctx) is not None


def test_support_resistance_signal():
    with build_session() as db:
        base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
        for i in range(19):
            add_candle(db, "EEE", "15m", base + timedelta(minutes=15 * i), 100, 105, 95, 100, 2000)
        add_candle(db, "EEE", "15m", base + timedelta(minutes=15 * 19), 106, 108, 105, 107, 2500)
        db.commit()
        strategy = SupportResistance()
        ctx = StrategyContext(ticker="EEE", timeframe="15m", now=base + timedelta(minutes=15 * 19), db=db)
        assert strategy.generate_signal(ctx) is not None
