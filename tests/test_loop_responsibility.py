import asyncio
from datetime import datetime, timezone

from app.domain.models import Signal
from app.loops.core import InMemorySignalQueue, LoopAExecutor, LoopBScanner
from app.strategies.registry import StrategyRegistry


class FakeStrategyEngine:
    def __init__(self) -> None:
        self.called = 0

    def scan_signals(self):
        self.called += 1
        return [Signal(index=1, side="buy", ticker="005930")]


class FakeOrderService:
    def __init__(self) -> None:
        self.executed: list[Signal] = []

    async def execute_from_signal(self, signal: Signal) -> None:
        self.executed.append(signal)


def test_loop_b_only_scans_and_enqueues():
    queue = InMemorySignalQueue(items=[])
    strategy = FakeStrategyEngine()
    loop_b = LoopBScanner(strategy_engine=strategy, queue=queue)
    count = loop_b.run_once()
    assert count == 1
    assert strategy.called == 1
    assert len(queue.items) == 1


def test_loop_a_only_consumes_and_executes():
    signal = Signal(index=1, side="buy", ticker="005930")
    queue = InMemorySignalQueue(items=[signal])
    order_service = FakeOrderService()
    loop_a = LoopAExecutor(order_service=order_service, queue=queue)
    did = asyncio.run(loop_a.run_once())
    assert did is True
    assert len(order_service.executed) == 1
    assert queue.items == []


def test_loop_b_timeframe_scan_with_registry():
    queue = InMemorySignalQueue(items=[])
    loop_b = LoopBScanner(strategy_engine=StrategyRegistry(), queue=queue)
    # 이 불변성 테스트에서는 메서드 연결과 비정상 종료가 없는지만 확인한다.
    count = loop_b.run_for_timeframe(
        timeframe="5m",
        ticker="005930",
        candles=[],
        now=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
    )
    assert isinstance(count, int)
    assert count >= 0
