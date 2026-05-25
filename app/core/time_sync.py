from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Protocol
from zoneinfo import ZoneInfo


class ServerTimeProvider(Protocol):
    async def get_server_time(self) -> datetime:
        raise NotImplementedError


class TimeSyncService:
    """
    서버 시간 오프셋을 메모리에 유지하고, 정렬된 현재 시각을 제공한다.
    """

    def __init__(
        self,
        *,
        provider: ServerTimeProvider,
        server_timezone: str = "Asia/Seoul",
        now_fn: Callable[[], datetime] | None = None,
        pre_market_sync_hour: int = 7,
        pre_market_sync_minute: int = 50,
        pre_market_window_minutes: int = 10,
        min_retry_seconds: int = 30,
    ) -> None:
        self.provider = provider
        self._tz = ZoneInfo(server_timezone)
        self.now_fn = now_fn or (lambda: datetime.now(self._tz))
        self.pre_market_sync_hour = pre_market_sync_hour
        self.pre_market_sync_minute = pre_market_sync_minute
        self.pre_market_window_minutes = pre_market_window_minutes
        self.min_retry_seconds = max(min_retry_seconds, 1)
        self._offset_seconds: float = 0.0
        self._last_synced_date: str | None = None
        self._last_attempt_at: datetime | None = None

    async def sync_offset_seconds(self) -> float:
        server_now = await self.provider.get_server_time()
        local_now = self.now_fn().astimezone(self._tz)
        if server_now.tzinfo is None:
            server_now = server_now.replace(tzinfo=self._tz)
        else:
            server_now = server_now.astimezone(self._tz)
        offset = (server_now - local_now).total_seconds()
        self._offset_seconds = float(offset)
        self._last_synced_date = local_now.date().isoformat()
        self._last_attempt_at = local_now
        return offset

    def aligned_now(self) -> datetime:
        return self.now_fn().astimezone(self._tz) + timedelta(seconds=self._offset_seconds)

    def offset_seconds(self) -> float:
        return self._offset_seconds

    async def sync_if_due_pre_market(self) -> float | None:
        now_local = self.now_fn().astimezone(self._tz)
        if not self._in_pre_market_sync_window(now_local):
            return None

        if self._last_synced_date == now_local.date().isoformat():
            return self._offset_seconds

        if self._last_attempt_at is not None:
            elapsed = (now_local - self._last_attempt_at).total_seconds()
            if elapsed < self.min_retry_seconds:
                return None

        self._last_attempt_at = now_local
        return await self.sync_offset_seconds()

    def _in_pre_market_sync_window(self, now_local: datetime) -> bool:
        current_minutes = now_local.hour * 60 + now_local.minute
        start = self.pre_market_sync_hour * 60 + self.pre_market_sync_minute
        end = start + self.pre_market_window_minutes
        return start <= current_minutes < end
