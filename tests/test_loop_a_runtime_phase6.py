import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.domain.models import OrderRequest, OrderResult, OrderStatus, Signal
from app.loops.core import InMemorySignalQueue
from app.loops.loop_a_runtime import LoopARunner
from app.orders.service import OrderService
from app.orders.state_machine import PositionStateMachine
from app.repositories.ordering import OrderingRepository
from app.db.models.ordering import Order, Position
from tests.utils import build_session_factory


class FakeSignalExecutor:
    def __init__(self) -> None:
        self.executed: list[Signal] = []

    async def execute_from_signal(self, signal: Signal) -> None:
        self.executed.append(signal)


class FakePriceProvider:
    def __init__(self, price_by_ticker: dict[str, float]) -> None:
        self.price_by_ticker = price_by_ticker

    async def get_current_price(self, ticker: str) -> float:
        return self.price_by_ticker[ticker]


class FakeAtrProvider:
    def __init__(self, atr_value: float) -> None:
        self.atr_value = atr_value

    async def get_atr(self, ticker: str, strategy_id: str) -> float:  # noqa: ARG002
        return self.atr_value


class SuccessGateway:
    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        return OrderResult(ok=True, order_id="CLOSE-1")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=True, status="filled", filled_qty=1.0)


class FailGateway:
    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        return OrderResult(ok=False, order_id="X", error="timeout")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=False, status="not_found", filled_qty=0.0)


def _create_open_position(maker, *, state: str = "OPEN") -> int:
    repo = OrderingRepository()
    with maker() as db:
        signal = repo.create_signal(
            db,
            ticker="005930",
            strategy_id="2",
            timeframe="15m",
            side="buy",
            signal_price=70000.0,
            signal_time=datetime.now(timezone.utc),
        )
        order = repo.create_order(
            db,
            signal_id=signal.id,
            external_order_id="OPEN-1",
            ticker="005930",
            side="buy",
            order_type="limit",
            price=70000.0,
            quantity=10.0,
            status="filled",
            reason=None,
        )
        position = repo.open_position(
            db,
            order_id=order.id,
            ticker="005930",
            strategy_id="2",
            entry_price=100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            quantity=10.0,
        )
        if state == "HALF_CLOSED":
            position.state = "HALF_CLOSED"
            position.remaining_quantity = 5.0
            position.highest_price = 112.0
            position.trailing_stop_price = 109.0
            db.commit()
        return position.id


def test_loop_a_runner_consumes_signal_and_half_closes_position():
    maker = build_session_factory()
    position_id = _create_open_position(maker, state="OPEN")
    queue = InMemorySignalQueue(items=[Signal(index=1, side="buy", ticker="000660")])
    signal_executor = FakeSignalExecutor()
    runner = LoopARunner(
        queue=queue,
        signal_executor=signal_executor,
        ordering_repo=OrderingRepository(),
        order_service=OrderService(SuccessGateway()),
        state_machine=PositionStateMachine(),
        price_provider=FakePriceProvider({"005930": 111.0}),
        atr_provider=FakeAtrProvider(atr_value=2.0),
        session_factory=maker,
    )

    result = asyncio.run(runner.run_once())
    assert result.executed_signal is True
    assert result.monitored_positions == 1
    assert result.failed_close_orders == 0
    assert len(signal_executor.executed) == 1

    with maker() as db:
        row = db.get(Position, position_id)
        assert row is not None
        assert row.state == "HALF_CLOSED"
        assert row.remaining_quantity == 5.0
        orders = db.scalars(select(Order).where(Order.side == "sell")).all()
        assert len(orders) == 1


def test_loop_a_runner_closes_on_trailing_stop():
    maker = build_session_factory()
    position_id = _create_open_position(maker, state="HALF_CLOSED")
    runner = LoopARunner(
        queue=InMemorySignalQueue(items=[]),
        signal_executor=FakeSignalExecutor(),
        ordering_repo=OrderingRepository(),
        order_service=OrderService(SuccessGateway()),
        state_machine=PositionStateMachine(),
        price_provider=FakePriceProvider({"005930": 108.0}),
        atr_provider=FakeAtrProvider(atr_value=2.0),
        session_factory=maker,
    )

    result = asyncio.run(runner.run_once())
    assert result.executed_signal is False
    assert result.closed_positions == 1

    with maker() as db:
        row = db.get(Position, position_id)
        assert row is not None
        assert row.state == "CLOSED"
        assert row.close_reason == "trailing_stop"
        assert row.remaining_quantity == 0.0


def test_loop_a_runner_keeps_position_when_close_order_fails():
    maker = build_session_factory()
    position_id = _create_open_position(maker, state="OPEN")
    runner = LoopARunner(
        queue=InMemorySignalQueue(items=[]),
        signal_executor=FakeSignalExecutor(),
        ordering_repo=OrderingRepository(),
        order_service=OrderService(FailGateway()),
        state_machine=PositionStateMachine(),
        price_provider=FakePriceProvider({"005930": 94.0}),
        atr_provider=FakeAtrProvider(atr_value=2.0),
        session_factory=maker,
    )

    result = asyncio.run(runner.run_once())
    assert result.failed_close_orders == 1

    with maker() as db:
        row = db.get(Position, position_id)
        assert row is not None
        assert row.state == "OPEN"
