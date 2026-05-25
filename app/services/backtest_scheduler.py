from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable

from app.domain.models import Candle, Signal
from app.services.backtest_jobs import BacktestJobService


class AutoBacktestScheduler:
    """
    Loop C-linked auto backtest scheduler (default: once a day after run_hour).
    """

    def __init__(
        self,
        *,
        backtest_service: BacktestJobService,
        candles_provider: Callable[[], list[Candle]],
        slippage_pct_provider: Callable[[], float] | None = None,
        now_fn: Callable[[], datetime] | None = None,
        enabled: bool = False,
        run_hour: int = 16,
        max_signals: int = 80,
    ) -> None:
        self.backtest_service = backtest_service
        self.candles_provider = candles_provider
        self.slippage_pct_provider = slippage_pct_provider or (lambda: 0.05)
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.enabled = enabled
        self.run_hour = run_hour
        self.max_signals = max_signals

        self.last_run_date: str | None = None
        self.last_job_id: str | None = None
        self.last_status: str | None = None
        self.last_reason: str | None = None
        self.last_checked_at: str | None = None
        self.last_job_snapshot: dict[str, object] | None = None
        self.last_job_completed_at: str | None = None

    async def trigger_if_due(self) -> dict[str, object]:
        now = self.now_fn()
        self.last_checked_at = now.isoformat()
        day = now.date().isoformat()

        if not self.enabled:
            return self._skip("disabled")
        if now.hour < self.run_hour:
            return self._skip(f"before_run_hour({self.run_hour})")
        if self.last_run_date == day:
            return self._skip("already_ran_today")

        return await self.trigger_now(reason="scheduled")

    async def trigger_now(self, *, reason: str = "manual") -> dict[str, object]:
        candles = self.candles_provider()
        if len(candles) < 2:
            return self._skip("insufficient_candles")
        signals = self._build_signals(candles)
        if not signals:
            return self._skip("no_signals")

        slippage_pct = min(max(float(self.slippage_pct_provider()), 0.0), 0.5)
        job_id = await self.backtest_service.start_job(candles=candles, signals=signals, slippage_pct=slippage_pct)
        now = self.now_fn()
        self.last_run_date = now.date().isoformat()
        self.last_job_id = job_id
        self.last_status = "triggered"
        self.last_reason = reason
        self.last_job_snapshot = None
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._watch_job(job_id), name=f"auto-backtest-watch-{job_id[:8]}")
        except RuntimeError:
            pass
        return {
            "ok": True,
            "triggered": True,
            "reason": reason,
            "job_id": job_id,
            "signal_count": len(signals),
            "candle_count": len(candles),
            "slippage_pct": slippage_pct,
            "triggered_at": now.isoformat(),
        }

    def trigger_if_due_background(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.trigger_if_due(), name="auto-backtest-trigger")

    def status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "run_hour": self.run_hour,
            "last_run_date": self.last_run_date,
            "last_job_id": self.last_job_id,
            "last_status": self.last_status,
            "last_reason": self.last_reason,
            "last_checked_at": self.last_checked_at,
            "last_job_completed_at": self.last_job_completed_at,
            "last_job_snapshot": self.last_job_snapshot,
        }

    def _skip(self, reason: str) -> dict[str, object]:
        self.last_status = "skipped"
        self.last_reason = reason
        return {"ok": True, "triggered": False, "reason": reason}

    def _build_signals(self, candles: list[Candle]) -> list[Signal]:
        end = len(candles) - 1
        if end <= 0:
            return []
        start = max(0, end - self.max_signals)
        out: list[Signal] = []
        for idx in range(start, end):
            side = "buy" if candles[idx].close >= candles[idx].open else "sell"
            out.append(Signal(index=idx, side=side, ticker="AUTO"))
        return out

    async def _watch_job(self, job_id: str, *, max_wait_seconds: int = 300) -> None:
        iterations = max(max_wait_seconds * 5, 5)
        for _ in range(iterations):
            row = await self.backtest_service.get_job(job_id)
            if row is None:
                return
            status = str(row.get("status"))
            if status in {"completed", "failed"}:
                self.last_job_snapshot = {
                    "job_id": row.get("job_id"),
                    "status": status,
                    "progress": row.get("progress"),
                    "result": row.get("result"),
                    "error": row.get("error"),
                }
                self.last_job_completed_at = self.now_fn().isoformat()
                return
            await asyncio.sleep(0.2)
