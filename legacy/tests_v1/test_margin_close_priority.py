import asyncio
from datetime import datetime, timezone

import app.loops.loop_a as loop_a_module
from app.db.models.position import Position
from app.orders.broker import FillResult
from app.risk.engine import RiskEngine
from app.runtime.signal_queue import SignalQueue
from app.runtime.state import RuntimeState
from app.loops.loop_a import LoopA
from tests.utils import build_session, reset_manager


class AlwaysFillBroker:
    async def place_exit_market(self, ticker: str, qty: float) -> FillResult:  # noqa: ARG002
        return FillResult(ok=True, order_id="ok", avg_price=0.0, filled_qty=qty, status="filled")


class FixedNow(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        return datetime(2026, 1, 1, 15, 21, tzinfo=tz)


def test_margin_close_uses_priority_order(monkeypatch):
    manager = reset_manager()
    with build_session() as db:
        manager.load(db)
        manager.set(db, "daily_base_capital", "150", changed_by="test")
        manager.set(db, "margin_close_priority", "1,2,3,5,4", changed_by="test")
        # 두 포지션 합계 200 -> 1개 청산 필요
        p1 = Position(
            ticker="AAA",
            strategy_id="1",
            state="OPEN",
            entry_price=100,
            stop_price=90,
            take_profit_price=120,
            trailing_stop_price=None,
            highest_price=100,
            quantity=1,
            remaining_quantity=1,
            entry_time=datetime.now(timezone.utc),
            closed_time=None,
            close_reason=None,
        )
        p2 = Position(
            ticker="BBB",
            strategy_id="4",
            state="OPEN",
            entry_price=100,
            stop_price=90,
            take_profit_price=120,
            trailing_stop_price=None,
            highest_price=100,
            quantity=1,
            remaining_quantity=1,
            entry_time=datetime.now(timezone.utc),
            closed_time=None,
            close_reason=None,
        )
        db.add_all([p1, p2])
        db.commit()

        state = RuntimeState()
        loop_a = LoopA(SignalQueue(), state, RiskEngine(manager), broker=AlwaysFillBroker())
        monkeypatch.setattr(loop_a_module, "datetime", FixedNow)
        asyncio.run(loop_a._run_margin_close_if_needed(db))  # noqa: SLF001

        db.refresh(p1)
        db.refresh(p2)
        assert p1.state == "CLOSED"
        assert p1.close_reason == "margin_forced_close"
        assert p2.state != "CLOSED"
