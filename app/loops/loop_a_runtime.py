from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.models import OrderRequest
from app.loops.core import InMemorySignalQueue
from app.orders.service import OrderService
from app.orders.state_machine import PositionSnapshot, PositionStateMachine
from app.repositories.ordering import OrderingRepository


class SessionFactory(Protocol):
    def __call__(self) -> Session:
        raise NotImplementedError


class SignalExecutor(Protocol):
    async def execute_from_signal(self, signal) -> None:  # noqa: ANN001
        raise NotImplementedError


class PriceProvider(Protocol):
    async def get_current_price(self, ticker: str) -> float:
        raise NotImplementedError


class AtrProvider(Protocol):
    async def get_atr(self, ticker: str, strategy_id: str) -> float:
        raise NotImplementedError


class CriticalSafety(Protocol):
    async def critical(self, *, code: str, message: str) -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class LoopAResult:
    executed_signal: bool
    monitored_positions: int
    closed_positions: int
    failed_close_orders: int


class LoopARunner:
    """
    Loop A runtime:
    - consume one queued signal and execute order pipeline
    - monitor open positions and apply state machine transitions
    - execute close orders on stop/take-profit/trailing transitions
    """

    def __init__(
        self,
        *,
        queue: InMemorySignalQueue,
        signal_executor: SignalExecutor,
        ordering_repo: OrderingRepository,
        order_service: OrderService,
        state_machine: PositionStateMachine,
        price_provider: PriceProvider,
        atr_provider: AtrProvider,
        session_factory: SessionFactory,
        safety: CriticalSafety | None = None,
        config: object | None = None,
        default_trail_atr_mult: float = 1.5,
    ) -> None:
        self.queue = queue
        self.signal_executor = signal_executor
        self.ordering_repo = ordering_repo
        self.order_service = order_service
        self.state_machine = state_machine
        self.price_provider = price_provider
        self.atr_provider = atr_provider
        self.session_factory = session_factory
        self.safety = safety
        self.config = config
        self.default_trail_atr_mult = default_trail_atr_mult

    async def run_once(self) -> LoopAResult:
        executed_signal = await self._consume_signal_once()
        monitored, closed, failed = await self._monitor_positions_once()
        return LoopAResult(
            executed_signal=executed_signal,
            monitored_positions=monitored,
            closed_positions=closed,
            failed_close_orders=failed,
        )

    async def _consume_signal_once(self) -> bool:
        signal = self.queue.pop_one()
        if signal is None:
            return False
        try:
            await self.signal_executor.execute_from_signal(signal)
            return True
        except Exception as exc:  # noqa: BLE001
            await self._critical(code="signal_execute_failed", message=str(exc))
            return False

    async def _monitor_positions_once(self) -> tuple[int, int, int]:
        try:
            with self.session_factory() as db:
                positions = self.ordering_repo.list_open_positions(db)
        except SQLAlchemyError as exc:
            await self._critical(code="positions_query_failed", message=str(exc))
            return 0, 0, 0

        monitored = 0
        closed = 0
        failed = 0
        for position in positions:
            monitored += 1
            current_price = await self.price_provider.get_current_price(position.ticker)
            atr_value = await self.atr_provider.get_atr(position.ticker, position.strategy_id)
            transition = self.state_machine.decide(
                position=PositionSnapshot(
                    state=position.state,
                    remaining_quantity=position.remaining_quantity,
                    stop_price=position.stop_price,
                    take_profit_price=position.take_profit_price,
                    trailing_stop_price=position.trailing_stop_price,
                    highest_price=position.highest_price,
                ),
                current_price=current_price,
                atr_value=atr_value,
                trail_atr_mult=self._resolve_trail_atr_mult(position.strategy_id),
            )

            try:
                db_ctx = self.session_factory()
            except SQLAlchemyError as exc:
                failed += 1
                await self._critical(code="positions_session_failed", message=str(exc))
                continue

            with db_ctx as db:
                if transition.close_qty > 0:
                    close_req = OrderRequest(
                        ticker=position.ticker,
                        side="sell",
                        order_type="market",
                        qty=transition.close_qty,
                        price=None,
                    )
                    order_result = await self.order_service.place_with_reconcile(close_req)
                    if not order_result.ok:
                        failed += 1
                        await self._critical(
                            code="close_order_failed",
                            message=(
                                f"{position.ticker} strategy={position.strategy_id} "
                                f"reason={transition.reason} error={order_result.error}"
                            ),
                        )
                        continue

                    try:
                        self.ordering_repo.create_order(
                            db,
                            signal_id=None,
                            external_order_id=order_result.order_id,
                            ticker=position.ticker,
                            side="sell",
                            order_type="market",
                            price=current_price,
                            quantity=transition.close_qty,
                            status="filled",
                            reason=transition.reason,
                        )
                        updated = self.ordering_repo.apply_transition(db, position.id, transition)
                        if updated.state == "CLOSED":
                            closed += 1
                    except SQLAlchemyError as exc:
                        failed += 1
                        await self._critical(code="position_update_failed", message=str(exc))
                    continue

                if (
                    transition.new_highest != position.highest_price
                    or transition.new_trailing_stop != position.trailing_stop_price
                ):
                    try:
                        self.ordering_repo.apply_transition(db, position.id, transition)
                    except SQLAlchemyError as exc:
                        failed += 1
                        await self._critical(code="position_update_failed", message=str(exc))

        return monitored, closed, failed

    async def _critical(self, *, code: str, message: str) -> None:
        if self.safety is None:
            return
        await self.safety.critical(code=code, message=message)

    def _resolve_trail_atr_mult(self, strategy_id: str) -> float:
        if self.config is None:
            return self.default_trail_atr_mult

        strategy_key = f"strategy.{strategy_id}.trail_atr_mult"
        try:
            value = self.config.get(strategy_key)
            return float(value)
        except (KeyError, ValueError, TypeError):
            pass

        return float(self.config.get("trail_atr_mult"))
