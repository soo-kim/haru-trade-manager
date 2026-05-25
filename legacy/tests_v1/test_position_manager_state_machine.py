import asyncio
from datetime import datetime, timezone

from app.db.models.position import Position
from app.orders.broker import FillResult
from app.orders.position_manager import PositionManager
from tests.utils import build_session


class AlwaysFillBroker:
    async def place_exit_market(self, ticker: str, qty: float) -> FillResult:  # noqa: ARG002
        return FillResult(ok=True, order_id="ok", avg_price=0.0, filled_qty=qty, status="filled")


def _make_open_position() -> Position:
    return Position(
        ticker="005930",
        strategy_id="2",
        state="OPEN",
        entry_price=100.0,
        stop_price=95.0,
        take_profit_price=110.0,
        trailing_stop_price=None,
        highest_price=100.0,
        quantity=10.0,
        remaining_quantity=10.0,
        entry_time=datetime.now(timezone.utc),
        closed_time=None,
        close_reason=None,
    )


def test_open_to_half_closed_on_take_profit():
    manager = PositionManager(broker=AlwaysFillBroker(), trail_atr_mult=1.5)
    with build_session() as db:
        p = _make_open_position()
        db.add(p)
        db.commit()
        db.refresh(p)

        asyncio.run(manager.monitor_and_close(db, p, current_price=111.0, atr_value=2.0))
        db.refresh(p)
        assert p.state == "HALF_CLOSED"
        assert p.remaining_quantity == 5.0
        assert p.trailing_stop_price is not None


def test_half_closed_to_closed_on_trailing_stop():
    manager = PositionManager(broker=AlwaysFillBroker(), trail_atr_mult=1.5)
    with build_session() as db:
        p = _make_open_position()
        p.state = "HALF_CLOSED"
        p.remaining_quantity = 5.0
        p.highest_price = 120.0
        p.trailing_stop_price = 117.0
        db.add(p)
        db.commit()
        db.refresh(p)

        asyncio.run(manager.monitor_and_close(db, p, current_price=116.0, atr_value=2.0))
        db.refresh(p)
        assert p.state == "CLOSED"
        assert p.close_reason == "trailing_stop"
        assert p.remaining_quantity == 0.0


def test_open_to_closed_on_stop_loss():
    manager = PositionManager(broker=AlwaysFillBroker(), trail_atr_mult=1.5)
    with build_session() as db:
        p = _make_open_position()
        db.add(p)
        db.commit()
        db.refresh(p)

        asyncio.run(manager.monitor_and_close(db, p, current_price=94.0, atr_value=2.0))
        db.refresh(p)
        assert p.state == "CLOSED"
        assert p.close_reason == "stop_loss"
