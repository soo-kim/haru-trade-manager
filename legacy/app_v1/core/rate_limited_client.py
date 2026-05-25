from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable


@dataclass(order=True)
class ClientTask:
    priority: int
    seq: int
    fn: Callable[[], Awaitable[Any]]


class RateLimitedClient:
    def __init__(self, min_interval_seconds: float = 0.2) -> None:
        self.min_interval_seconds = min_interval_seconds
        self._lock = asyncio.Lock()
        self._queue: asyncio.PriorityQueue[ClientTask] = asyncio.PriorityQueue()
        self._last_request_time = 0.0
        self._seq = 0

        self._access_token: str | None = None
        self._expires_at: datetime | None = None

    async def set_token(self, token: str, expires_in_seconds: int) -> None:
        self._access_token = token
        self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)

    def token_expiring_soon(self) -> bool:
        if self._expires_at is None:
            return True
        return datetime.now(timezone.utc) >= self._expires_at - timedelta(minutes=5)

    async def enqueue(self, fn: Callable[[], Awaitable[Any]], is_order: bool = False) -> Any:
        priority = 0 if is_order else 1
        self._seq += 1
        task = ClientTask(priority=priority, seq=self._seq, fn=fn)
        await self._queue.put(task)
        return await self._drain_one()

    async def _drain_one(self) -> Any:
        task = await self._queue.get()
        try:
            async with self._lock:
                elapsed = time.monotonic() - self._last_request_time
                remaining = self.min_interval_seconds - elapsed
                if remaining > 0:
                    await asyncio.sleep(remaining)

                result = await task.fn()
                self._last_request_time = time.monotonic()
                return result
        finally:
            self._queue.task_done()
