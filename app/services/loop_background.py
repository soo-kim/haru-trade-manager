from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from app.services.loop_runtime import CycleReport


class LoopCoordinator(Protocol):
    async def run_cycle(self) -> CycleReport:
        raise NotImplementedError


@dataclass
class LoopBackgroundStatus:
    running: bool
    interval_seconds: float
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_duration_ms: float | None
    last_error: str | None
    cycles: int


class LoopBackgroundRunner:
    def __init__(self, *, coordinator: LoopCoordinator, interval_seconds: float = 1.0) -> None:
        self.coordinator = coordinator
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

        self._last_started_at: datetime | None = None
        self._last_completed_at: datetime | None = None
        self._last_duration_ms: float | None = None
        self._last_error: str | None = None
        self._cycles = 0

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> bool:
        if self.is_running():
            return False
        self._task = asyncio.create_task(self._run_loop(), name="loop-background-runner")
        return True

    async def stop(self) -> bool:
        if not self.is_running():
            return False
        assert self._task is not None
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        return True

    def status(self) -> LoopBackgroundStatus:
        return LoopBackgroundStatus(
            running=self.is_running(),
            interval_seconds=self.interval_seconds,
            last_started_at=self._last_started_at,
            last_completed_at=self._last_completed_at,
            last_duration_ms=self._last_duration_ms,
            last_error=self._last_error,
            cycles=self._cycles,
        )

    async def _run_loop(self) -> None:
        while True:
            self._last_started_at = datetime.now(timezone.utc)
            started = time.monotonic()
            try:
                report = await self.coordinator.run_cycle()
                self._last_error = report.error
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
            finally:
                self._cycles += 1
                self._last_duration_ms = (time.monotonic() - started) * 1000
                self._last_completed_at = datetime.now(timezone.utc)

            delay = self.interval_seconds - ((time.monotonic() - started) or 0)
            if delay > 0:
                await asyncio.sleep(delay)
