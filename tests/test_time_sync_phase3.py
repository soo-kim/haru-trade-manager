import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.time_sync import TimeSyncService


class FakeServerTimeProvider:
    def __init__(self, server_time: datetime) -> None:
        self.server_time = server_time

    async def get_server_time(self) -> datetime:
        return self.server_time


def test_time_sync_updates_offset_and_aligned_now():
    local_now = datetime(2026, 1, 1, 9, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    server_now = local_now + timedelta(seconds=7)
    svc = TimeSyncService(
        provider=FakeServerTimeProvider(server_now),
        server_timezone="Asia/Seoul",
        now_fn=lambda: local_now,
    )

    offset = asyncio.run(svc.sync_offset_seconds())
    assert offset == 7.0
    assert svc.offset_seconds() == 7.0
    assert svc.aligned_now() == server_now
