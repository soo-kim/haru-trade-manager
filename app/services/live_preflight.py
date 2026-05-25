from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from app.core.settings import settings
from app.services.loop_runtime import LoopRuntimeCoordinator
from app.services.runtime_state import RuntimeState


@dataclass(frozen=True)
class PreflightCheck:
    key: str
    ok: bool
    detail: str
    required: bool = True


@dataclass(frozen=True)
class RehearsalReport:
    ok: bool
    cycles: int
    succeeded: int
    failed: int
    preflight_ok: bool
    errors: list[str]
    started_at: str
    completed_at: str


class LivePreflightService:
    def __init__(
        self,
        *,
        runtime: RuntimeState,
        loop_runtime: LoopRuntimeCoordinator,
        background_status: Callable[[], dict[str, Any]],
        connectivity_checker: Callable[[str | None], Awaitable[dict[str, object]]],
    ) -> None:
        self.runtime = runtime
        self.loop_runtime = loop_runtime
        self.background_status = background_status
        self.connectivity_checker = connectivity_checker

    async def run(self, *, stage: str = "market", ticker: str | None = None) -> dict[str, object]:
        policy = self._policy_for(stage)
        checks: list[PreflightCheck] = []
        mode_live = settings.trading_mode.lower() == "live"
        checks.append(
            PreflightCheck(
                key="trading_mode_live",
                ok=mode_live,
                detail=f"TRADING_MODE={settings.trading_mode}",
                required=True,
            )
        )
        checks.append(
            PreflightCheck(
                key="runtime_not_halted",
                ok=not self.runtime.halted,
                detail=self.runtime.halt_reason or "ok",
                required=True,
            )
        )

        bg = self.background_status()
        checks.append(
            PreflightCheck(
                key="background_running",
                ok=(bg.get("running") is True) if policy["require_background"] else True,
                detail=f"running={bg.get('running')}",
                required=policy["require_background"],
            )
        )

        tickers = self.loop_runtime.tickers_provider()
        checks.append(
            PreflightCheck(
                key="runtime_tickers_present",
                ok=len(tickers) > 0,
                detail=f"count={len(tickers)}",
                required=policy["require_tickers"],
            )
        )

        connectivity = await self.connectivity_checker(ticker)
        conn_ok = bool(connectivity.get("ok", False))
        checks.append(
            PreflightCheck(
                key="kiwoom_connectivity",
                ok=conn_ok,
                detail=str(connectivity),
                required=policy["require_connectivity"],
            )
        )

        required_failed = [c for c in checks if c.required and not c.ok]
        ok = len(required_failed) == 0
        return {
            "ok": ok,
            "stage": stage,
            "stage_policy": policy,
            "checks": [
                {"key": c.key, "ok": c.ok, "detail": c.detail, "required": c.required}
                for c in checks
            ],
            "failed_checks": [c.key for c in required_failed],
            "actions": self._actions(required_failed),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    async def run_rehearsal(
        self,
        *,
        stage: str = "market",
        ticker: str | None = None,
        cycles: int = 3,
    ) -> RehearsalReport:
        started = datetime.now(timezone.utc)
        preflight = await self.run(stage=stage, ticker=ticker)
        if not preflight["ok"]:
            return RehearsalReport(
                ok=False,
                cycles=cycles,
                succeeded=0,
                failed=cycles,
                preflight_ok=False,
                errors=[f"사전점검실패: {', '.join(preflight['failed_checks'])}"],
                started_at=started.isoformat(),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )

        succeeded = 0
        failed = 0
        errors: list[str] = []
        for _ in range(max(cycles, 1)):
            report = await self.loop_runtime.run_cycle()
            if report.ok:
                succeeded += 1
            else:
                failed += 1
                if report.error:
                    errors.append(report.error)

        return RehearsalReport(
            ok=failed == 0,
            cycles=max(cycles, 1),
            succeeded=succeeded,
            failed=failed,
            preflight_ok=True,
            errors=errors,
            started_at=started.isoformat(),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _actions(failed: list[PreflightCheck]) -> list[str]:
        action_map = {
            "trading_mode_live": "TRADING_MODE를 live로 변경한 뒤 서비스를 재시작하세요.",
            "runtime_not_halted": "정지 사유를 해소한 뒤 /telegram /resume 명령으로 재개하세요.",
            "background_running": "/system/loops/start 로 백그라운드 루프를 시작하세요.",
            "runtime_tickers_present": "유니버스를 먼저 초기화/리밸런싱하세요. (최초 실행 시 코스피200+코스닥150 자동 초기화)",
            "kiwoom_connectivity": "연결 점검을 실행하고 키움 인증정보/네트워크를 확인하세요.",
        }
        actions: list[str] = []
        for item in failed:
            if item.key in action_map:
                actions.append(action_map[item.key])
        return actions

    @staticmethod
    def _policy_for(stage: str) -> dict[str, bool]:
        normalized = stage.strip().lower()
        policies = {
            "pre_market": {
                "require_background": True,
                "require_tickers": True,
                "require_connectivity": True,
            },
            "market": {
                "require_background": True,
                "require_tickers": True,
                "require_connectivity": True,
            },
            "post_market": {
                "require_background": False,
                "require_tickers": False,
                "require_connectivity": False,
            },
        }
        return policies.get(normalized, policies["market"])
