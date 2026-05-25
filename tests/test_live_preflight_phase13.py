import asyncio

from app.core.settings import settings
from app.loops.loop_a_runtime import LoopAResult
from app.services.live_preflight import LivePreflightService
from app.services.loop_runtime import LoopRuntimeCoordinator
from app.services.runtime_state import RuntimeState


class FakeLoopA:
    async def run_once(self) -> LoopAResult:
        return LoopAResult(
            executed_signal=False,
            monitored_positions=0,
            closed_positions=0,
            failed_close_orders=0,
        )


class FakeLoopB:
    async def run_once_for_ticker(self, ticker: str) -> int:  # noqa: ARG002
        return 0


class FakeLoopC:
    def run_once(self) -> None:
        return


async def _connectivity_ok(_: str | None) -> dict[str, object]:
    return {"ok": True, "enabled": True}


async def _connectivity_fail(_: str | None) -> dict[str, object]:
    return {"ok": False, "enabled": True}


def _build_service(runtime: RuntimeState, *, running: bool = True, tickers: list[str] | None = None) -> LivePreflightService:
    coordinator = LoopRuntimeCoordinator(
        loop_a=FakeLoopA(),
        loop_b=FakeLoopB(),
        loop_c=FakeLoopC(),
        tickers_provider=lambda: tickers if tickers is not None else ["005930"],
    )
    return LivePreflightService(
        runtime=runtime,
        loop_runtime=coordinator,
        background_status=lambda: {"running": running},
        connectivity_checker=_connectivity_ok,
    )


def test_live_preflight_fails_when_not_live_mode():
    original_mode = settings.trading_mode
    settings.trading_mode = "paper"
    try:
        service = _build_service(RuntimeState(), running=False, tickers=[])
        result = asyncio.run(service.run(stage="market"))
        assert result["ok"] is False
        assert "trading_mode_live" in result["failed_checks"]
    finally:
        settings.trading_mode = original_mode


def test_live_preflight_success_case():
    original_mode = settings.trading_mode
    settings.trading_mode = "live"
    try:
        service = _build_service(RuntimeState(), running=True, tickers=["005930"])
        result = asyncio.run(service.run(stage="market"))
        assert result["ok"] is True
        assert result["failed_checks"] == []
    finally:
        settings.trading_mode = original_mode


def test_live_rehearsal_runs_cycles_after_preflight():
    original_mode = settings.trading_mode
    settings.trading_mode = "live"
    try:
        service = _build_service(RuntimeState(), running=True, tickers=["005930"])
        report = asyncio.run(service.run_rehearsal(stage="market", cycles=5))
        assert report.preflight_ok is True
        assert report.cycles == 5
        assert report.succeeded == 5
        assert report.failed == 0
    finally:
        settings.trading_mode = original_mode


def test_live_preflight_post_market_policy_relaxes_requirements():
    original_mode = settings.trading_mode
    settings.trading_mode = "live"
    try:
        coordinator = LoopRuntimeCoordinator(
            loop_a=FakeLoopA(),
            loop_b=FakeLoopB(),
            loop_c=FakeLoopC(),
            tickers_provider=lambda: [],
        )
        service = LivePreflightService(
            runtime=RuntimeState(),
            loop_runtime=coordinator,
            background_status=lambda: {"running": False},
            connectivity_checker=_connectivity_fail,
        )
        result = asyncio.run(service.run(stage="post_market"))
        assert result["ok"] is True
        assert result["stage_policy"]["require_background"] is False
        assert result["stage_policy"]["require_connectivity"] is False
    finally:
        settings.trading_mode = original_mode
