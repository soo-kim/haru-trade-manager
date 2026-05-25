import asyncio

from app.loops.loop_a_runtime import LoopAResult
from app.services.loop_runtime import LoopRuntimeCoordinator


class SoakLoopA:
    async def run_once(self) -> LoopAResult:
        return LoopAResult(
            executed_signal=False,
            monitored_positions=0,
            closed_positions=0,
            failed_close_orders=0,
        )


class SoakLoopB:
    async def run_once_for_ticker(self, ticker: str) -> int:  # noqa: ARG002
        return 0


class SoakLoopC:
    def run_once(self) -> None:
        return


async def _run_many(coordinator: LoopRuntimeCoordinator, cycles: int) -> None:
    for _ in range(cycles):
        report = await coordinator.run_cycle()
        assert report.ok is True


def test_runtime_soak_many_cycles():
    coordinator = LoopRuntimeCoordinator(
        loop_a=SoakLoopA(),
        loop_b=SoakLoopB(),
        loop_c=SoakLoopC(),
        tickers_provider=lambda: ["005930", "000660"],
    )
    asyncio.run(_run_many(coordinator, cycles=200))
    health = coordinator.health_snapshot()
    assert health["cycle_count"] == 200
    assert health["error_count"] == 0
    assert health["degraded"] is False
