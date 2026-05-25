from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.kiwoom.gateway import KiwoomGateway, OrderRequest, OrderResult, OrderStatus


class MockKiwoomGateway(KiwoomGateway):
    async def place_order(self, request: OrderRequest) -> OrderResult:  # noqa: ARG002
        return OrderResult(ok=True, order_id="live-mock-order")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=True, status="filled", filled_quantity=1.0)

    async def get_server_time(self) -> datetime:
        return datetime.now(timezone.utc)
