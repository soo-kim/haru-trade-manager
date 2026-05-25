from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class OrderRequest:
    ticker: str
    side: str
    order_type: str
    quantity: float
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
    filled_quantity: float


class KiwoomGateway(Protocol):
    async def place_order(self, request: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_order_status(self, order_id: str) -> OrderStatus:
        raise NotImplementedError

    async def get_server_time(self) -> datetime:
        raise NotImplementedError
