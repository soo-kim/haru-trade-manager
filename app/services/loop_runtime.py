from __future__ import annotations

import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.loops.loop_a_runtime import LoopAResult


class LoopARunnable(Protocol):
    async def run_once(self) -> LoopAResult:
        raise NotImplementedError


class LoopBRunnable(Protocol):
    async def run_once_for_ticker(self, ticker: str) -> int:
        raise NotImplementedError


class LoopCRunnable(Protocol):
    def run_once(self) -> None:
        raise NotImplementedError


class CriticalSafety(Protocol):
    async def critical(self, *, code: str, message: str) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class CycleReport:
    ok: bool
    loop_a: LoopAResult
    loop_b_signals: int
    loop_c_ran: bool
    duration_ms: float
    error: str | None = None


@dataclass
class LoopRuntimeMetrics:
    cycle_count: int = 0
    error_count: int = 0
    consecutive_errors: int = 0
    last_error: str | None = None
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    last_loop_b_signals: int = 0
    last_loop_c_ran: bool = False


class LoopRuntimeCoordinator:
    """
    Single runtime coordinator for loop A/B/C execution + health metrics.
    """

    def __init__(
        self,
        *,
        loop_a: LoopARunnable,
        loop_b: LoopBRunnable,
        loop_c: LoopCRunnable,
        tickers_provider: Callable[[], list[str]],
        safety: CriticalSafety | None = None,
        maintenance_interval_minutes: int = 30,
        expected_cycle_seconds: float = 5.0,
        now_fn: Callable[[], datetime] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
        extra_metrics_provider: Callable[[], dict[str, object]] | None = None,
        pre_loop_b_hook: Callable[[], object] | None = None,
        strategy_enabled_provider: Callable[[], bool] | None = None,
    ) -> None:
        self.loop_a = loop_a
        self.loop_b = loop_b
        self.loop_c = loop_c
        self.tickers_provider = tickers_provider
        self.safety = safety
        self.maintenance_interval_minutes = maintenance_interval_minutes
        self.expected_cycle_seconds = expected_cycle_seconds
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.monotonic_fn = monotonic_fn or time.monotonic
        self.extra_metrics_provider = extra_metrics_provider
        self.pre_loop_b_hook = pre_loop_b_hook
        self.strategy_enabled_provider = strategy_enabled_provider or (lambda: True)

        self.metrics = LoopRuntimeMetrics()
        self._last_loop_c_slot: str | None = None
        self._total_duration_ms = 0.0

    async def run_cycle(self) -> CycleReport:
        started = self.now_fn()
        start_mono = self.monotonic_fn()
        self.metrics.last_started_at = started

        default_a = LoopAResult(
            executed_signal=False,
            monitored_positions=0,
            closed_positions=0,
            failed_close_orders=0,
        )
        try:
            strategy_enabled = self.strategy_enabled_provider()
            loop_a_result = await self.loop_a.run_once() if strategy_enabled else default_a
            if self.pre_loop_b_hook is not None:
                maybe_awaitable = self.pre_loop_b_hook()
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
            loop_b_signals = 0
            for ticker in self.tickers_provider():
                loop_b_signals += await self.loop_b.run_once_for_ticker(ticker)

            loop_c_ran = self._should_run_loop_c(self.now_fn())
            if loop_c_ran:
                maybe_awaitable = self.loop_c.run_once()
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable

            duration = (self.monotonic_fn() - start_mono) * 1000
            self._record_success(duration_ms=duration, loop_b_signals=loop_b_signals, loop_c_ran=loop_c_ran)
            return CycleReport(
                ok=True,
                loop_a=loop_a_result,
                loop_b_signals=loop_b_signals,
                loop_c_ran=loop_c_ran,
                duration_ms=duration,
            )
        except Exception as exc:  # noqa: BLE001
            duration = (self.monotonic_fn() - start_mono) * 1000
            self._record_failure(duration_ms=duration, error=str(exc))
            if self.safety is not None:
                await self.safety.critical(code="loop_cycle_failed", message=str(exc))
            return CycleReport(
                ok=False,
                loop_a=default_a,
                loop_b_signals=0,
                loop_c_ran=False,
                duration_ms=duration,
                error=str(exc),
            )

    def health_snapshot(self) -> dict[str, object]:
        lag_ms = None
        if self.metrics.last_completed_at is not None:
            elapsed = (self.now_fn() - self.metrics.last_completed_at).total_seconds()
            lag_ms = max((elapsed - self.expected_cycle_seconds) * 1000, 0.0)

        degraded = self.metrics.consecutive_errors >= 3
        data: dict[str, object] = {
            "cycle_count": self.metrics.cycle_count,
            "error_count": self.metrics.error_count,
            "consecutive_errors": self.metrics.consecutive_errors,
            "last_error": self.metrics.last_error,
            "last_started_at": self._iso(self.metrics.last_started_at),
            "last_completed_at": self._iso(self.metrics.last_completed_at),
            "last_duration_ms": self.metrics.last_duration_ms,
            "avg_duration_ms": self.metrics.avg_duration_ms,
            "max_duration_ms": self.metrics.max_duration_ms,
            "last_loop_b_signals": self.metrics.last_loop_b_signals,
            "last_loop_c_ran": self.metrics.last_loop_c_ran,
            "cycle_lag_ms": lag_ms,
            "degraded": degraded,
            "strategy_loops_enabled": self.strategy_enabled_provider(),
        }
        if self.extra_metrics_provider is not None:
            try:
                extra = self.extra_metrics_provider()
                if isinstance(extra, dict):
                    data.update(extra)
            except Exception:  # noqa: BLE001
                pass
        return data

    def _should_run_loop_c(self, now: datetime) -> bool:
        minute = now.minute
        if minute % self.maintenance_interval_minutes != 0:
            return False
        slot = now.strftime("%Y-%m-%d %H:") + f"{minute:02d}"
        if self._last_loop_c_slot == slot:
            return False
        self._last_loop_c_slot = slot
        return True

    def _record_success(self, *, duration_ms: float, loop_b_signals: int, loop_c_ran: bool) -> None:
        self.metrics.cycle_count += 1
        self.metrics.consecutive_errors = 0
        self.metrics.last_error = None
        self.metrics.last_completed_at = self.now_fn()
        self.metrics.last_duration_ms = duration_ms
        self.metrics.last_loop_b_signals = loop_b_signals
        self.metrics.last_loop_c_ran = loop_c_ran
        self._total_duration_ms += duration_ms
        self.metrics.avg_duration_ms = self._total_duration_ms / self.metrics.cycle_count
        self.metrics.max_duration_ms = max(self.metrics.max_duration_ms, duration_ms)

    def _record_failure(self, *, duration_ms: float, error: str) -> None:
        self.metrics.cycle_count += 1
        self.metrics.error_count += 1
        self.metrics.consecutive_errors += 1
        self.metrics.last_error = error
        self.metrics.last_completed_at = self.now_fn()
        self.metrics.last_duration_ms = duration_ms
        self.metrics.last_loop_b_signals = 0
        self.metrics.last_loop_c_ran = False
        self._total_duration_ms += duration_ms
        self.metrics.avg_duration_ms = self._total_duration_ms / self.metrics.cycle_count
        self.metrics.max_duration_ms = max(self.metrics.max_duration_ms, duration_ms)

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.isoformat()
