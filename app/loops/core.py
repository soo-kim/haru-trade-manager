from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.domain.models import Signal
from app.risk.engine import PositionExposure, RiskEngine


@dataclass
class InMemorySignalQueue:
    items: list[Signal]

    def put_many(self, signals: Iterable[Signal]) -> None:
        self.items.extend(signals)

    def pop_one(self) -> Signal | None:
        if not self.items:
            return None
        return self.items.pop(0)


class LoopBScanner:
    """
    Loop B responsibility: scan strategies and enqueue signals only.
    """

    def __init__(self, strategy_engine: object, queue: InMemorySignalQueue) -> None:
        self.strategy_engine = strategy_engine
        self.queue = queue

    def run_once(self) -> int:
        signals = list(self.strategy_engine.scan_signals())
        self.queue.put_many(signals)
        return len(signals)

    def run_for_timeframe(self, *, timeframe: str, ticker: str, candles: list, now) -> int:  # noqa: ANN001
        if not hasattr(self.strategy_engine, "scan"):
            raise TypeError("strategy_engine must provide scan() for timeframe mode")
        signals = list(self.strategy_engine.scan(timeframe=timeframe, ticker=ticker, candles=candles, now=now))
        self.queue.put_many(signals)
        return len(signals)


class LoopAExecutor:
    """
    Loop A responsibility: consume queue and execute orders only.
    """

    def __init__(self, order_service: object, queue: InMemorySignalQueue) -> None:
        self.order_service = order_service
        self.queue = queue

    async def run_once(self) -> bool:
        signal = self.queue.pop_one()
        if signal is None:
            return False
        await self.order_service.execute_from_signal(signal)
        return True


class LoopAPositionManager:
    """
    Loop A responsibility extension:
    position monitoring and forced close decision.
    """

    def __init__(self, *, risk_engine: RiskEngine, ordering_repo: object, config: object) -> None:
        self.risk_engine = risk_engine
        self.ordering_repo = ordering_repo
        self.config = config

    def resolve_margin_forced_close(self, exposures: list[PositionExposure]) -> list[int]:
        base_capital = float(self.config.get("daily_base_capital"))
        priority = [x.strip() for x in self.config.get("margin_close_priority").split(",") if x.strip()]
        return self.risk_engine.margin_forced_close_order(
            exposures=exposures,
            daily_base_capital=base_capital,
            priority=priority,
        )


class LoopCMaintainer:
    """
    Loop C responsibility:
    maintenance only (universe refresh / optimization / reporting trigger).
    """

    def __init__(self, maintenance_service: object) -> None:
        self.maintenance_service = maintenance_service

    def run_once(self) -> None:
        post_market_hook = getattr(self.maintenance_service, "schedule_post_market_backfill_if_due", None)
        if callable(post_market_hook):
            post_market_hook()
        self.maintenance_service.refresh_universe()
        self.maintenance_service.optimize_parameters()
        self.maintenance_service.aggregate_daily_performance()
