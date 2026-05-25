import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.db.models.universe import Symbol
from app.db.session import SessionLocal
from app.runtime.signal_queue import SignalQueue
from app.runtime.state import RuntimeState
from app.strategies.base import StrategyContext
from app.strategies.registry import build_default_strategies

logger = logging.getLogger(__name__)


class LoopB:
    def __init__(self, queue: SignalQueue, state: RuntimeState) -> None:
        self.queue = queue
        self.state = state
        self.strategies = build_default_strategies()
        self._processed_close_keys: set[tuple[str, str, str, str]] = set()

    @staticmethod
    def _is_candle_close(now: datetime, timeframe: str) -> bool:
        if timeframe == "5m":
            return now.minute % 5 == 0
        if timeframe == "15m":
            return now.minute % 15 == 0
        if timeframe in {"60m", "1h"}:
            return now.minute == 0
        return False

    @staticmethod
    def _active_tickers() -> list[str]:
        with SessionLocal() as db:
            tickers = db.scalars(
                select(Symbol.ticker).where(Symbol.is_active.is_(True), Symbol.is_blocked.is_(False))
            ).all()
        return tickers

    async def tick(self, now: datetime | None = None) -> None:
        if self.state.paused_all:
            await asyncio.sleep(0.1)
            return

        now = now or (datetime.now() + timedelta(seconds=self.state.server_time_offset_sec))
        tickers = self._active_tickers()
        with SessionLocal() as db:
            for ticker in tickers:
                for strategy in self.strategies:
                    if not strategy.is_active_now(now):
                        continue
                    if not self._is_candle_close(now, strategy.timeframe):
                        continue
                    close_key = (
                        ticker,
                        strategy.strategy_id,
                        strategy.timeframe,
                        now.strftime("%Y-%m-%d %H:%M"),
                    )
                    if close_key in self._processed_close_keys:
                        continue

                    context = StrategyContext(ticker=ticker, timeframe=strategy.timeframe, now=now, db=db)
                    event = strategy.generate_signal(context)
                    self._processed_close_keys.add(close_key)
                    if event is not None:
                        await self.queue.put(event)
                        logger.info("signal queued", extra={"event": "signal_queued"})

    async def run(self) -> None:
        while not self.state.stop_requested:
            await self.tick()
            await asyncio.sleep(1.0)
