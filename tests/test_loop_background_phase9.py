import asyncio

from app.loops.loop_a_runtime import LoopAResult
from app.services.loop_background import LoopBackgroundRunner
from app.services.loop_runtime import CycleReport


class FakeCoordinator:
    def __init__(self) -> None:
        self.calls = 0

    async def run_cycle(self) -> CycleReport:
        self.calls += 1
        return CycleReport(
            ok=True,
            loop_a=LoopAResult(
                executed_signal=False,
                monitored_positions=0,
                closed_positions=0,
                failed_close_orders=0,
            ),
            loop_b_signals=0,
            loop_c_ran=False,
            duration_ms=1.0,
            error=None,
        )


async def _run_background() -> tuple[int, object]:
    coordinator = FakeCoordinator()
    runner = LoopBackgroundRunner(coordinator=coordinator, interval_seconds=0.01)
    started = await runner.start()
    await asyncio.sleep(0.05)
    stopped = await runner.stop()
    status = runner.status()
    return coordinator.calls, (started, stopped, status)


def test_loop_background_runner_start_stop():
    calls, meta = asyncio.run(_run_background())
    started, stopped, status = meta
    assert started is True
    assert stopped is True
    assert calls >= 2
    assert status.running is False
    assert status.cycles >= 2
