import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import OrderRequest, OrderResult, OrderStatus, Signal
from app.orders.service import OrderService
from app.repositories.ordering import OrderingRepository
from app.risk.engine import RiskEngine
from app.services.trading_service import TradingService
from app.db.models.ordering import Order, Position, Signal as SignalRow
import app.db.models  # noqa: F401
from tests.utils import build_session_factory


class SuccessGateway:
    async def place_order(self, req: OrderRequest) -> OrderResult:  # noqa: ARG002
        return OrderResult(ok=True, order_id="OID-1")

    async def get_order_status(self, order_id: str) -> OrderStatus:  # noqa: ARG002
        return OrderStatus(exists=True, status="filled", filled_qty=1.0)


def test_execute_from_signal_persists_order_and_position():
    maker = build_session_factory()

    svc = TradingService(
        order_service=OrderService(SuccessGateway()),
        ordering_repo=OrderingRepository(),
        risk_engine=RiskEngine(),
        session_factory=maker,
    )
    signal = Signal(
        index=1,
        side="buy",
        ticker="005930",
        strategy_id="2",
        timeframe="15m",
        price=70000.0,
        signal_time=datetime.now(timezone.utc),
    )

    asyncio.run(svc.execute_from_signal(signal))

    with maker() as db:
        signals = db.scalars(select(SignalRow)).all()
        orders = db.scalars(select(Order)).all()
        positions = db.scalars(select(Position)).all()
        assert len(signals) == 1
        assert len(orders) == 1
        assert orders[0].status == "filled"
        assert len(positions) == 1
        assert positions[0].state == "OPEN"
