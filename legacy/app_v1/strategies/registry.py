from app.strategies.base import Strategy
from app.strategies.impl.ema_pullback import EmaPullback
from app.strategies.impl.gap_momentum import GapMomentum
from app.strategies.impl.support_resistance import SupportResistance
from app.strategies.impl.volatility_breakout import VolatilityBreakout
from app.strategies.impl.volume_surge import VolumeSurge


def build_default_strategies() -> list[Strategy]:
    return [
        GapMomentum(),
        EmaPullback(),
        VolatilityBreakout(),
        VolumeSurge(),
        SupportResistance(),
    ]
