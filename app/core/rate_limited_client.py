from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class Job:
    priority: int
    seq: int
    fn: Callable[[], Awaitable[Any]]
    future: asyncio.Future[Any] = field(compare=False)


class RateLimitedClient:
    def __init__(self, min_interval: float = 0.2) -> None:
        self.min_interval = min_interval
        self._last_ts = 0.0
        self._seq = 0
        self._seq_lock = asyncio.Lock()
        self._queue: asyncio.PriorityQueue[Job] = asyncio.PriorityQueue()
        self._worker_task: asyncio.Task[None] | None = None
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    async def submit(self, fn: Callable[[], Awaitable[Any]], *, is_order: bool = False) -> Any:
        loop = asyncio.get_running_loop()
        async with self._seq_lock:
            self._seq += 1
            seq = self._seq
        fut: asyncio.Future[Any] = loop.create_future()
        await self._queue.put(Job(priority=0 if is_order else 1, seq=seq, fn=fn, future=fut))
        self._ensure_worker(loop)
        return await fut

    async def enqueue(self, fn: Callable[[], Awaitable[Any]], *, is_order: bool = False) -> Any:
        return await self.submit(fn, is_order=is_order)

    async def set_token(self, token: str, expires_in_seconds: int) -> None:
        self._token = token
        self._token_expires_at = time.monotonic() + max(expires_in_seconds, 0)

    def get_token(self) -> str | None:
        return self._token

    def token_expiring(self, *, buffer_seconds: int = 300) -> bool:
        if not self._token:
            return True
        return (self._token_expires_at - time.monotonic()) <= buffer_seconds

    def _ensure_worker(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = loop.create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                elapsed = time.monotonic() - self._last_ts
                if elapsed < self.min_interval:
                    await asyncio.sleep(self.min_interval - elapsed)
                result = await job.fn()
                self._last_ts = time.monotonic()
                if not job.future.done():
                    job.future.set_result(result)
            except Exception as exc:  # noqa: BLE001
                if not job.future.done():
                    job.future.set_exception(exc)
            finally:
                self._queue.task_done()
