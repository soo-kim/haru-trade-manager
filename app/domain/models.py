from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candle:
    open: float
    high: float
    low: float
    close: float
    ts: datetime
    volume: float = 0.0


@dataclass(frozen=True)
class Signal:
    index: int
    side: str
    ticker: str
    strategy_id: str = "default"
    timeframe: str = "5m"
    price: float | None = None
    signal_time: datetime | None = None


@dataclass(frozen=True)
class OrderRequest:
    ticker: str
    side: str
    order_type: str
    qty: float
    price: float | None


@dataclass(frozen=True)
class OrderResult:
    ok: bool
    order_id: str | None
    error: str | None = None


@dataclass(frozen=True)
class OrderStatus:
    exists: bool
    status: str
    filled_qty: float = 0.0
