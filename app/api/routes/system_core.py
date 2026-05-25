from __future__ import annotations

from datetime import datetime
from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel


class ConfigSetRequest(BaseModel):
    key: str
    value: str
    changed_by: str = "api"


class TelegramCommandRequest(BaseModel):
    command: str


def create_system_core_router(
    *,
    config_service,
    runtime_snapshot_provider: Callable[[], dict[str, object]],
    loop_background,
    loop_runtime,
    telegram_service,
    daily_reporter,
    live_preflight,
    live_connectivity_checker,
) -> APIRouter:
    router = APIRouter()

    @router.get("/config")
    def get_config() -> dict[str, str]:
        return config_service.get_all()

    @router.post("/config")
    def set_config(req: ConfigSetRequest) -> dict[str, str]:
        config_service.set(key=req.key, value=req.value, changed_by=req.changed_by)
        return {"status": "ok", "key": req.key, "value": req.value}

    @router.get("/system/runtime")
    def get_runtime() -> dict[str, object]:
        return runtime_snapshot_provider()

    @router.post("/telegram/command")
    def telegram_command(req: TelegramCommandRequest) -> dict[str, object]:
        result = telegram_service.handle(req.command)
        return {"ok": result.ok, "message": result.message}

    @router.post("/system/loops/run-cycle")
    async def run_cycle() -> dict[str, object]:
        result = await loop_runtime.run_cycle()
        return {
            "ok": result.ok,
            "loop_a": {
                "executed_signal": result.loop_a.executed_signal,
                "monitored_positions": result.loop_a.monitored_positions,
                "closed_positions": result.loop_a.closed_positions,
                "failed_close_orders": result.loop_a.failed_close_orders,
            },
            "loop_b_signals": result.loop_b_signals,
            "loop_c_ran": result.loop_c_ran,
            "duration_ms": result.duration_ms,
            "error": result.error,
        }

    @router.post("/system/loops/start")
    async def start_loops() -> dict[str, object]:
        started = await loop_background.start()
        status = loop_background.status()
        return {
            "ok": True,
            "started": started,
            "running": status.running,
            "interval_seconds": status.interval_seconds,
        }

    @router.post("/system/loops/stop")
    async def stop_loops() -> dict[str, object]:
        stopped = await loop_background.stop()
        status = loop_background.status()
        return {
            "ok": True,
            "stopped": stopped,
            "running": status.running,
        }

    @router.post("/system/reports/daily")
    async def send_daily_report(target_date: str | None = None) -> dict[str, object]:
        day = datetime.now().date() if target_date is None else datetime.fromisoformat(target_date).date()
        text = daily_reporter.build_report_text(day)
        sent = await daily_reporter.send_report_once_per_day(day)
        return {"ok": True, "date": day.isoformat(), "sent": sent, "report": text}

    @router.post("/system/reports/weekly")
    async def send_weekly_report(target_date: str | None = None, days: int = 7) -> dict[str, object]:
        day = datetime.now().date() if target_date is None else datetime.fromisoformat(target_date).date()
        text = daily_reporter.build_weekly_report_text(day, days=max(days, 1))
        sent = await daily_reporter.send_weekly_report_once_per_week(day, days=max(days, 1))
        return {"ok": True, "end_date": day.isoformat(), "days": max(days, 1), "sent": sent, "report": text}

    @router.post("/system/live/connectivity-check")
    async def live_connectivity_check(ticker: str | None = None) -> dict[str, object]:
        return await live_connectivity_checker(ticker=ticker)

    @router.post("/system/live/preflight")
    async def live_preflight_check(stage: str = "market", ticker: str | None = None) -> dict[str, object]:
        return await live_preflight.run(stage=stage, ticker=ticker)

    @router.post("/system/live/rehearsal")
    async def live_rehearsal(stage: str = "market", ticker: str | None = None, cycles: int = 3) -> dict[str, object]:
        report = await live_preflight.run_rehearsal(stage=stage, ticker=ticker, cycles=cycles)
        return {
            "ok": report.ok,
            "cycles": report.cycles,
            "succeeded": report.succeeded,
            "failed": report.failed,
            "preflight_ok": report.preflight_ok,
            "errors": report.errors,
            "started_at": report.started_at,
            "completed_at": report.completed_at,
        }

    return router
