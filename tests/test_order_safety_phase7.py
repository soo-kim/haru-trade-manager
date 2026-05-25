import asyncio

from app.domain.models import OrderRequest, OrderResult, OrderStatus
from app.orders.service import OrderService
from app.services.runtime_safety import RuntimeSafetyManager
from app.services.runtime_state import RuntimeState


class StatusRaiseGateway:
    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        return OrderResult(ok=False, order_id="A", error="timeout")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        raise RuntimeError("status endpoint down")


class UnresolvedGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        self.calls += 1
        return OrderResult(ok=False, order_id=f"X{self.calls}", error="timeout")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=False, status="not_found")


def test_order_service_halts_on_status_check_failure():
    runtime = RuntimeState()
    safety = RuntimeSafetyManager(runtime=runtime)
    service = OrderService(StatusRaiseGateway(), safety=safety)
    req = OrderRequest(ticker="005930", side="buy", order_type="limit", qty=1, price=70000)

    result = asyncio.run(service.place_with_reconcile(req))
    assert result.ok is False
    assert result.error == "status_check_failed"
    assert runtime.halted is True
    assert runtime.halt_reason is not None
    assert "order_status_check_failed" in runtime.halt_reason


def test_order_service_halts_on_unresolved_reconcile():
    runtime = RuntimeState()
    safety = RuntimeSafetyManager(runtime=runtime)
    service = OrderService(UnresolvedGateway(), safety=safety)
    req = OrderRequest(ticker="005930", side="buy", order_type="limit", qty=1, price=70000)

    result = asyncio.run(service.place_with_reconcile(req))
    assert result.ok is False
    assert runtime.halted is True
    assert runtime.halt_reason is not None
    assert "order_unresolved" in runtime.halt_reason
