import asyncio

from app.integrations.kiwoom.gateway import OrderRequest, OrderResult, OrderStatus
from app.orders.safe_order_service import SafeOrderService


class FakeGateway:
    def __init__(self, first: OrderResult, second: OrderResult, status: OrderStatus):
        self.first = first
        self.second = second
        self.status = status
        self.calls = 0
        self.status_calls = 0

    async def place_order(self, request: OrderRequest) -> OrderResult:  # noqa: ARG002
        self.calls += 1
        return self.first if self.calls == 1 else self.second

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        self.status_calls += 1
        return self.status


def test_order_failure_must_check_status_before_retry():
    gateway = FakeGateway(
        first=OrderResult(ok=False, order_id="abc", error="timeout"),
        second=OrderResult(ok=False, order_id="def", error="timeout"),
        status=OrderStatus(exists=True, status="accepted", filled_quantity=0.0),
    )
    service = SafeOrderService(gateway)
    request = OrderRequest(ticker="005930", side="buy", order_type="limit", quantity=1, price=10000)

    result = asyncio.run(service.place_with_reconcile(request))
    assert result.ok is True
    assert gateway.status_calls == 1
    assert gateway.calls == 1
