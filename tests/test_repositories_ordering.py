from datetime import datetime, timezone

from app.repositories.ordering import OrderingRepository
from tests.utils import build_session


def test_ordering_repository_signal_order_position_lifecycle():
    repo = OrderingRepository()
    with build_session() as db:
        signal = repo.create_signal(
            db,
            ticker="005930",
            strategy_id="2",
            timeframe="15m",
            side="buy",
            signal_price=70000.0,
            signal_time=datetime.now(timezone.utc),
        )
        order = repo.create_order(
            db,
            signal_id=signal.id,
            external_order_id="x1",
            ticker="005930",
            side="buy",
            order_type="limit",
            price=70000.0,
            quantity=1.0,
            status="filled",
            reason=None,
        )
        position = repo.open_position(
            db,
            order_id=order.id,
            ticker="005930",
            strategy_id="2",
            entry_price=70000.0,
            stop_price=69000.0,
            take_profit_price=72000.0,
            quantity=1.0,
        )

        open_rows = repo.list_open_positions(db)
        assert len(open_rows) == 1
        assert open_rows[0].id == position.id

        closed = repo.mark_position_closed(db, position.id, reason="manual")
        assert closed.state == "CLOSED"
        assert closed.close_reason == "manual"
        assert len(repo.list_open_positions(db)) == 0


def test_ordering_repository_list_and_count_positions():
    repo = OrderingRepository()
    with build_session() as db:
        signal = repo.create_signal(
            db,
            ticker="005930",
            strategy_id="1",
            timeframe="5m",
            side="buy",
            signal_price=70000.0,
            signal_time=datetime.now(timezone.utc),
        )
        order = repo.create_order(
            db,
            signal_id=signal.id,
            external_order_id="x2",
            ticker="005930",
            side="buy",
            order_type="limit",
            price=70000.0,
            quantity=1.0,
            status="filled",
            reason=None,
        )
        p1 = repo.open_position(
            db,
            order_id=order.id,
            ticker="005930",
            strategy_id="1",
            entry_price=70000.0,
            stop_price=69000.0,
            take_profit_price=72000.0,
            quantity=1.0,
        )
        p2 = repo.open_position(
            db,
            order_id=order.id,
            ticker="000660",
            strategy_id="2",
            entry_price=120000.0,
            stop_price=118000.0,
            take_profit_price=125000.0,
            quantity=1.0,
        )
        repo.mark_position_closed(db, p2.id, reason="manual")

        all_rows = repo.list_positions(db, offset=0, limit=10)
        open_rows = repo.list_positions(db, state="OPEN", offset=0, limit=10)

        assert len(all_rows) == 2
        assert len(open_rows) == 1
        assert open_rows[0].id == p1.id
        assert repo.count_positions(db) == 2
        assert repo.count_positions(db, state="OPEN") == 1
