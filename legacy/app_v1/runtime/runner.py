from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine

from app.core.config_manager import ConfigManager
from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings
from app.integrations.kiwoom.mock_gateway import MockKiwoomGateway
from app.integrations.kiwoom.real_gateway import RealKiwoomGateway
from app.integrations.kiwoom.rest_client import KiwoomRestClient
from app.integrations.telegram.client import TelegramClient
from app.loops.loop_a import LoopA
from app.loops.loop_b import LoopB
from app.loops.loop_c import LoopC
from app.orders.broker import LiveBroker, PaperBroker
from app.risk.engine import RiskEngine
from app.runtime.signal_queue import SignalQueue
from app.runtime.state import RuntimeState
from app.services.time_sync_service import TimeSyncService

logger = logging.getLogger(__name__)


class RuntimeRunner:
    def __init__(self, manager: ConfigManager) -> None:
        self.state = RuntimeState()
        self.queue = SignalQueue()
        self.risk_engine = RiskEngine(manager)
        self.rate_client = RateLimitedClient(min_interval_seconds=0.2)
        if settings.trading_mode == "live":
            if not settings.kiwoom_account_no:
                raise RuntimeError("KIWOOM_ACCOUNT_NO is required for live mode")
            gateway = RealKiwoomGateway(
                KiwoomRestClient(self.rate_client),
                account_no=settings.kiwoom_account_no,
            )
            broker = LiveBroker(gateway)
        else:
            gateway = MockKiwoomGateway()
            broker = PaperBroker()
        notifier = TelegramClient(self.rate_client)
        self.time_sync = TimeSyncService(gateway, self.state)
        self.loop_a = LoopA(self.queue, self.state, self.risk_engine, broker=broker, notifier=notifier)
        self.loop_b = LoopB(self.queue, self.state)
        self.loop_c = LoopC(self.state, manager=manager)
        self.tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        coroutines: list[Coroutine[None, None, None]] = [
            self.loop_a.run(),
            self.loop_b.run(),
            self.loop_c.run(),
        ]
        self.tasks = [asyncio.create_task(coro) for coro in coroutines]
        asyncio.create_task(self._sync_server_time())

    async def _sync_server_time(self) -> None:
        try:
            await self.time_sync.sync()
        except Exception as exc:  # noqa: BLE001
            logger.warning("server time sync failed: %s", exc)

    async def stop(self) -> None:
        self.state.stop_requested = True
        if not self.tasks:
            return
        await asyncio.gather(*self.tasks, return_exceptions=True)
