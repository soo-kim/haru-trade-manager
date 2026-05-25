import asyncio
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.position import Position
from app.db.session import SessionLocal
from app.market.price_provider import PriceProvider
from app.orders.broker import Broker
from app.orders.executor import OrderExecutor
from app.orders.position_manager import PositionManager
from app.risk.engine import RiskEngine
from app.runtime.signal_queue import SignalQueue
from app.runtime.state import RuntimeState

logger = logging.getLogger(__name__)


class LoopA:
    def __init__(
        self,
        queue: SignalQueue,
        state: RuntimeState,
        risk_engine: RiskEngine,
        broker: Broker,
        notifier: object | None = None,
    ) -> None:
        self.queue = queue
        self.state = state
        self.risk_engine = risk_engine
        self.order_executor = OrderExecutor(broker=broker, risk_engine=risk_engine, notifier=notifier)
        self.price_provider = PriceProvider()
        self.position_manager = PositionManager(broker=broker, trail_atr_mult=risk_engine.trail_atr_mult())

    def _count_open_positions(self, db: Session) -> int:
        count = db.scalar(select(func.count()).select_from(Position).where(Position.state != "CLOSED"))
        return int(count or 0)

    async def _monitor_positions(self, db: Session) -> None:
        open_positions = db.scalars(select(Position).where(Position.state != "CLOSED")).all()
        for position in open_positions:
            price = self.price_provider.get_last_price(db, position.ticker, timeframe="5m")
            if price is None:
                continue
            atr_value = self.risk_engine.compute_atr_value(db, position.ticker, timeframe="5m", fallback_price=price)
            await self.position_manager.monitor_and_close(db, position, price, atr_value)

    async def _run_margin_close_if_needed(self, db: Session) -> None:
        now = datetime.now()
        day_key = now.strftime("%Y-%m-%d")
        margin_close_time = self.risk_engine.manager.get("margin_close_time")
        hh, mm = margin_close_time.split(":")
        should_run = now.hour == int(hh) and now.minute >= int(mm)
        if not should_run or self.state.last_margin_close_date == day_key:
            return

        base_capital = float(self.risk_engine.manager.get("daily_base_capital"))
        positions = db.scalars(select(Position).where(Position.state != "CLOSED")).all()
        total_eval = 0.0
        for p in positions:
            price = self.price_provider.get_last_price(db, p.ticker, timeframe="5m") or p.entry_price
            total_eval += price * p.remaining_quantity
        if total_eval <= base_capital:
            self.state.last_margin_close_date = day_key
            return

        priority = [x.strip() for x in self.risk_engine.manager.get("margin_close_priority").split(",") if x.strip()]
        # strategy_id가 숫자가 아닐 수 있으므로 suffix 매핑을 허용한다.
        ordered = sorted(
            positions,
            key=lambda p: priority.index(p.strategy_id) if p.strategy_id in priority else len(priority),
        )
        for p in ordered:
            await self.position_manager.force_close(db, p, reason="margin_forced_close")

            positions_left = db.scalars(select(Position).where(Position.state != "CLOSED")).all()
            recalculated = 0.0
            for left in positions_left:
                left_price = self.price_provider.get_last_price(db, left.ticker, timeframe="5m") or left.entry_price
                recalculated += left_price * left.remaining_quantity
            if recalculated <= base_capital:
                break
        self.state.last_margin_close_date = day_key

    async def tick(self) -> None:
        if self.state.paused_all:
            await asyncio.sleep(0.05)
            return

        with SessionLocal() as db:
            if not self.state.paused_entry and not self.queue.empty():
                event = await self.queue.get()
                try:
                    open_positions = self._count_open_positions(db)
                    if not self.risk_engine.can_open_new_position(open_positions):
                        logger.warning("blocked by max_positions", extra={"event": "risk_block"})
                    else:
                        await self.order_executor.execute_signal(db, event)
                finally:
                    self.queue.task_done()

            await self._monitor_positions(db)
            await self._run_margin_close_if_needed(db)

    async def run(self) -> None:
        while not self.state.stop_requested:
            await self.tick()
