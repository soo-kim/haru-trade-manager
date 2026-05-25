from app.orders.state_machine import PositionSnapshot, PositionStateMachine


def test_open_to_half_closed_then_closed_by_trailing():
    sm = PositionStateMachine()
    open_pos = PositionSnapshot(
        state="OPEN",
        remaining_quantity=10.0,
        stop_price=95.0,
        take_profit_price=110.0,
        trailing_stop_price=None,
        highest_price=100.0,
    )
    t1 = sm.decide(position=open_pos, current_price=111.0, atr_value=2.0, trail_atr_mult=1.5)
    assert t1.new_state == "HALF_CLOSED"
    assert t1.close_qty == 5.0

    half_pos = PositionSnapshot(
        state="HALF_CLOSED",
        remaining_quantity=5.0,
        stop_price=95.0,
        take_profit_price=110.0,
        trailing_stop_price=t1.new_trailing_stop,
        highest_price=t1.new_highest,
    )
    t2 = sm.decide(position=half_pos, current_price=107.0, atr_value=2.0, trail_atr_mult=1.5)
    assert t2.new_state == "CLOSED"
    assert t2.reason == "trailing_stop"


def test_open_to_closed_on_stop_loss():
    sm = PositionStateMachine()
    open_pos = PositionSnapshot(
        state="OPEN",
        remaining_quantity=10.0,
        stop_price=95.0,
        take_profit_price=110.0,
        trailing_stop_price=None,
        highest_price=100.0,
    )
    t = sm.decide(position=open_pos, current_price=94.0, atr_value=2.0, trail_atr_mult=1.5)
    assert t.new_state == "CLOSED"
    assert t.reason == "stop_loss"
