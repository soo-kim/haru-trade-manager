import asyncio
import logging
from datetime import datetime

from app.core.config_manager import ConfigManager
from app.db.session import SessionLocal
from app.runtime.state import RuntimeState
from app.services.universe_service import UniverseService

logger = logging.getLogger(__name__)


class LoopC:
    def __init__(self, state: RuntimeState, manager: ConfigManager) -> None:
        self.state = state
        self.manager = manager
        self.universe_service = UniverseService()

    async def tick(self) -> None:
        if self.state.paused_all:
            await asyncio.sleep(0.1)
            return
        with SessionLocal() as db:
            threshold = float(self.manager.get("liquidity_threshold"))
            changed = self.universe_service.refresh_active_universe(db, threshold)
        logger.info(
            "maintenance tick",
            extra={"event": "maintenance_tick", "at": datetime.now().isoformat(), "active_changed": changed},
        )

    async def run(self) -> None:
        while not self.state.stop_requested:
            await self.tick()
            await asyncio.sleep(30 * 60)
