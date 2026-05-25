from __future__ import annotations

from app.domain.models import OrderRequest, OrderResult, OrderStatus


class PaperOrderGateway:
    """
    Simple in-process paper gateway.
    """

    def __init__(self) -> None:
        self._seq = 0

    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        self._seq += 1
        return OrderResult(ok=True, order_id=f"PAPER-{self._seq}")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=True, status="filled", filled_qty=1.0)
