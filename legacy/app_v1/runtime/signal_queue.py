from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class SignalEvent:
    ticker: str
    strategy_id: str
    timeframe: str
    signal_type: str
    side: str
    price: float
    signal_time: datetime


class SignalQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[SignalEvent] = asyncio.Queue()

    async def put(self, event: SignalEvent) -> None:
        await self._queue.put(event)

    async def get(self) -> SignalEvent:
        return await self._queue.get()

    def empty(self) -> bool:
        return self._queue.empty()

    def task_done(self) -> None:
        self._queue.task_done()
