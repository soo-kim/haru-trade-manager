import asyncio
from datetime import datetime, timezone

from app.domain.models import OrderRequest, OrderResult, OrderStatus
from app.loops.core import InMemorySignalQueue
from app.loops.loop_a_runtime import LoopARunner
from app.orders.service import OrderService
from app.orders.state_machine import PositionStateMachine
from app.repositories.ordering import OrderingRepository
from app.services.runtime_safety import RuntimeSafetyManager
from app.services.runtime_state import RuntimeState
from tests.test_loop_a_runtime_phase6 import FakeAtrProvider, FakePriceProvider, FakeSignalExecutor, _create_open_position
from tests.utils import build_session_factory


class AlwaysFailGateway:
    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        return OrderResult(ok=False, order_id="FAIL-1", error="timeout")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=False, status="not_found")


def test_loop_a_failed_close_halts_runtime():
    maker = build_session_factory()
    _create_open_position(maker, state="OPEN")
    runtime = RuntimeState()
    safety = RuntimeSafetyManager(runtime=runtime)

    runner = LoopARunner(
        queue=InMemorySignalQueue(items=[]),
        signal_executor=FakeSignalExecutor(),
        ordering_repo=OrderingRepository(),
        order_service=OrderService(AlwaysFailGateway(), safety=safety),
        state_machine=PositionStateMachine(),
        price_provider=FakePriceProvider({"005930": 94.0}),
        atr_provider=FakeAtrProvider(atr_value=2.0),
        session_factory=maker,
        safety=safety,
    )

    result = asyncio.run(runner.run_once())
    assert result.failed_close_orders == 1
    assert runtime.halted is True
    assert runtime.halt_reason is not None
    assert "close_order_failed" in runtime.halt_reason or "order_unresolved" in runtime.halt_reason
