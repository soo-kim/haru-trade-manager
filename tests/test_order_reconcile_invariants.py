import asyncio

from app.domain.models import OrderRequest, OrderResult, OrderStatus
from app.orders.service import OrderService


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        self.calls.append("place")
        if len([x for x in self.calls if x == "place"]) == 1:
            return OrderResult(ok=False, order_id="A", error="timeout")
        return OrderResult(ok=True, order_id="B")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        self.calls.append("status")
        return OrderStatus(exists=False, status="not_found")


def test_status_check_happens_before_retry():
    gateway = FakeGateway()
    service = OrderService(gateway)
    req = OrderRequest(ticker="005930", side="buy", order_type="limit", qty=1, price=10000)
    result = asyncio.run(service.place_with_reconcile(req))
    assert result.ok is True
    assert gateway.calls[:3] == ["place", "status", "place"]
