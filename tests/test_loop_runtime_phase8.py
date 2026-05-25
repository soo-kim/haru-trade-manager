import asyncio
from datetime import datetime, timezone

from app.loops.loop_a_runtime import LoopAResult
from app.services.loop_runtime import LoopRuntimeCoordinator


class FakeLoopA:
    def __init__(self) -> None:
        self.calls = 0

    async def run_once(self) -> LoopAResult:
        self.calls += 1
        return LoopAResult(
            executed_signal=self.calls > 0,
            monitored_positions=1,
            closed_positions=0,
            failed_close_orders=0,
        )


class FakeLoopB:
    def __init__(self, count: int = 1) -> None:
        self.count = count
        self.calls: list[str] = []

    async def run_once_for_ticker(self, ticker: str) -> int:
        self.calls.append(ticker)
        return self.count


class FakeLoopC:
    def __init__(self) -> None:
        self.calls = 0

    def run_once(self) -> None:
        self.calls += 1


class FakeSafety:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def critical(self, *, code: str, message: str) -> None:
        self.calls.append((code, message))


def test_loop_runtime_coordinator_success_and_loop_c_slot_dedupe():
    now = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    values = iter([100.0, 100.1, 100.2, 100.3])
    loop_a = FakeLoopA()
    loop_b = FakeLoopB(count=2)
    loop_c = FakeLoopC()

    coordinator = LoopRuntimeCoordinator(
        loop_a=loop_a,
        loop_b=loop_b,
        loop_c=loop_c,
        tickers_provider=lambda: ["005930", "000660"],
        now_fn=lambda: now,
        monotonic_fn=lambda: next(values),
    )

    first = asyncio.run(coordinator.run_cycle())
    second = asyncio.run(coordinator.run_cycle())

    assert first.ok is True
    assert first.loop_b_signals == 4
    assert first.loop_c_ran is True
    assert second.ok is True
    assert second.loop_c_ran is False
    assert loop_c.calls == 1

    health = coordinator.health_snapshot()
    assert health["cycle_count"] == 2
    assert health["error_count"] == 0
    assert health["degraded"] is False


class RaiseLoopB:
    async def run_once_for_ticker(self, ticker: str) -> int:  # noqa: ARG002
        raise RuntimeError("loop-b-fail")


def test_loop_runtime_coordinator_failure_records_error_and_calls_safety():
    now = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)
    safety = FakeSafety()
    coordinator = LoopRuntimeCoordinator(
        loop_a=FakeLoopA(),
        loop_b=RaiseLoopB(),
        loop_c=FakeLoopC(),
        tickers_provider=lambda: ["005930"],
        safety=safety,
        now_fn=lambda: now,
        monotonic_fn=lambda: 200.0,
    )

    report = asyncio.run(coordinator.run_cycle())
    assert report.ok is False
    assert report.error is not None
    assert "loop-b-fail" in report.error

    health = coordinator.health_snapshot()
    assert health["error_count"] == 1
    assert health["consecutive_errors"] == 1
    assert safety.calls and safety.calls[0][0] == "loop_cycle_failed"
