from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.kiwoom.gateway import KiwoomGateway
from app.runtime.state import RuntimeState


class TimeSyncService:
    def __init__(self, gateway: KiwoomGateway, state: RuntimeState) -> None:
        self.gateway = gateway
        self.state = state

    async def sync(self) -> float:
        server_now = await self.gateway.get_server_time()
        local_now = datetime.now(timezone.utc)
        offset = (server_now - local_now).total_seconds()
        self.state.server_time_offset_sec = offset
        return offset
