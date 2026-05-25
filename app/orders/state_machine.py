from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class PositionSnapshot:
    state: str
    remaining_quantity: float
    stop_price: float
    take_profit_price: float
    trailing_stop_price: float | None
    highest_price: float | None


@dataclass(frozen=True)
class Transition:
    new_state: str
    close_qty: float
    reason: str | None
    new_highest: float | None
    new_trailing_stop: float | None


class PositionStateMachine:
    def decide(
        self,
        *,
        position: PositionSnapshot,
        current_price: float,
        atr_value: float,
        trail_atr_mult: float,
    ) -> Transition:
        if position.state == "OPEN":
            if current_price <= position.stop_price:
                return Transition(
                    new_state="CLOSED",
                    close_qty=position.remaining_quantity,
                    reason="stop_loss",
                    new_highest=position.highest_price,
                    new_trailing_stop=position.trailing_stop_price,
                )
            if current_price >= position.take_profit_price:
                return Transition(
                    new_state="HALF_CLOSED",
                    close_qty=position.remaining_quantity / 2.0,
                    reason="take_profit_half",
                    new_highest=current_price,
                    new_trailing_stop=current_price - (atr_value * trail_atr_mult),
                )
            return Transition(
                new_state="OPEN",
                close_qty=0.0,
                reason=None,
                new_highest=position.highest_price,
                new_trailing_stop=position.trailing_stop_price,
            )

        if position.state == "HALF_CLOSED":
            highest = max(position.highest_price or current_price, current_price)
            trailing = highest - (atr_value * trail_atr_mult)
            if current_price <= trailing:
                return Transition(
                    new_state="CLOSED",
                    close_qty=position.remaining_quantity,
                    reason="trailing_stop",
                    new_highest=highest,
                    new_trailing_stop=trailing,
                )
            return Transition(
                new_state="HALF_CLOSED",
                close_qty=0.0,
                reason=None,
                new_highest=highest,
                new_trailing_stop=trailing,
            )

        return Transition(
            new_state=position.state,
            close_qty=0.0,
            reason=None,
            new_highest=position.highest_price,
            new_trailing_stop=position.trailing_stop_price,
        )

    def apply(self, position_obj, transition: Transition):  # noqa: ANN001
        position_obj.state = transition.new_state
        position_obj.highest_price = transition.new_highest
        position_obj.trailing_stop_price = transition.new_trailing_stop
        if transition.close_qty > 0:
            position_obj.remaining_quantity = max(position_obj.remaining_quantity - transition.close_qty, 0.0)
        if transition.new_state == "CLOSED":
            position_obj.closed_time = datetime.now(timezone.utc)
            if transition.reason:
                position_obj.close_reason = transition.reason
