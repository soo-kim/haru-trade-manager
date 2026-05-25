from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.integrations.kiwoom.gateway import KiwoomGateway, OrderRequest
from app.orders.safe_order_service import SafeOrderService


@dataclass(frozen=True)
class FillResult:
    ok: bool
    order_id: str | None
    avg_price: float
    filled_qty: float
    status: str
    error: str | None = None


class Broker(Protocol):
    async def place_entry(self, ticker: str, qty: float, price: float) -> FillResult:
        raise NotImplementedError

    async def place_exit_market(self, ticker: str, qty: float) -> FillResult:
        raise NotImplementedError


class PaperBroker:
    async def place_entry(self, ticker: str, qty: float, price: float) -> FillResult:  # noqa: ARG002
        return FillResult(ok=True, order_id="paper-entry", avg_price=price, filled_qty=qty, status="filled")

    async def place_exit_market(self, ticker: str, qty: float) -> FillResult:  # noqa: ARG002
        return FillResult(ok=True, order_id="paper-exit", avg_price=0.0, filled_qty=qty, status="filled")


class LiveBroker:
    def __init__(self, gateway: KiwoomGateway) -> None:
        self.safe_order_service = SafeOrderService(gateway)

    async def place_entry(self, ticker: str, qty: float, price: float) -> FillResult:
        result = await self.safe_order_service.place_with_reconcile(
            OrderRequest(
                ticker=ticker,
                side="buy",
                order_type="limit",
                quantity=qty,
                price=price,
            )
        )
        return FillResult(
            ok=result.ok,
            order_id=result.order_id,
            avg_price=price,
            filled_qty=qty if result.ok else 0.0,
            status="filled" if result.ok else "rejected",
            error=result.error,
        )

    async def place_exit_market(self, ticker: str, qty: float) -> FillResult:
        result = await self.safe_order_service.place_with_reconcile(
            OrderRequest(
                ticker=ticker,
                side="sell",
                order_type="market",
                quantity=qty,
                price=None,
            )
        )
        return FillResult(
            ok=result.ok,
            order_id=result.order_id,
            avg_price=0.0,
            filled_qty=qty if result.ok else 0.0,
            status="filled" if result.ok else "rejected",
            error=result.error,
        )
