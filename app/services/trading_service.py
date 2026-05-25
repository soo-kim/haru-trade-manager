from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.orm import Session

from app.domain.models import OrderRequest, Signal
from app.orders.service import OrderService
from app.repositories.ordering import OrderingRepository
from app.risk.engine import RiskEngine


class SessionFactory(Protocol):
    def __call__(self) -> Session:
        raise NotImplementedError


class TradingService:
    """
    Loop A execution service:
    - consume signal
    - order placement with reconcile
    - persist signal/order/position
    """

    def __init__(
        self,
        *,
        order_service: OrderService,
        ordering_repo: OrderingRepository,
        risk_engine: RiskEngine,
        session_factory: SessionFactory,
    ) -> None:
        self.order_service = order_service
        self.ordering_repo = ordering_repo
        self.risk_engine = risk_engine
        self.session_factory = session_factory

    async def execute_from_signal(self, signal: Signal) -> None:
        with self.session_factory() as db:
            db_signal = self.ordering_repo.create_signal(
                db,
                ticker=signal.ticker,
                strategy_id=signal.strategy_id,
                timeframe=signal.timeframe,
                side=signal.side,
                signal_price=signal.price or 0.0,
                signal_time=signal.signal_time or datetime.now(timezone.utc),
                status="queued",
            )

            req = OrderRequest(
                ticker=signal.ticker,
                side=signal.side,
                order_type="limit",
                qty=1.0,
                price=signal.price,
            )
            result = await self.order_service.place_with_reconcile(req)
            order = self.ordering_repo.create_order(
                db,
                signal_id=db_signal.id,
                external_order_id=result.order_id,
                ticker=signal.ticker,
                side=signal.side,
                order_type=req.order_type,
                price=req.price,
                quantity=req.qty,
                status="filled" if result.ok else "rejected",
                reason=result.error,
            )

            if result.ok:
                stop, tp = self.risk_engine.build_stop_take_profit(
                    entry_price=req.price or 0.0,
                    atr_value=max((req.price or 0.0) * 0.01, 1.0),
                    stop_atr_mult=1.5,
                    tp_atr_mult=2.0,
                )
                self.ordering_repo.open_position(
                    db,
                    order_id=order.id,
                    ticker=signal.ticker,
                    strategy_id=signal.strategy_id,
                    entry_price=req.price or 0.0,
                    stop_price=stop,
                    take_profit_price=tp,
                    quantity=req.qty,
                )
