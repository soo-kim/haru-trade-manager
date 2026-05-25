from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.ordering import Order, Position, Signal
from app.orders.state_machine import Transition


class OrderingRepository:
    def create_signal(
        self,
        db: Session,
        *,
        ticker: str,
        strategy_id: str,
        timeframe: str,
        side: str,
        signal_price: float,
        signal_time: datetime,
        status: str = "queued",
    ) -> Signal:
        row = Signal(
            ticker=ticker,
            strategy_id=strategy_id,
            timeframe=timeframe,
            side=side,
            signal_price=signal_price,
            signal_time=signal_time,
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def create_order(
        self,
        db: Session,
        *,
        signal_id: int | None,
        external_order_id: str | None,
        ticker: str,
        side: str,
        order_type: str,
        price: float | None,
        quantity: float,
        status: str,
        reason: str | None,
    ) -> Order:
        row = Order(
            signal_id=signal_id,
            external_order_id=external_order_id,
            ticker=ticker,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            filled_quantity=0.0,
            status=status,
            reason=reason,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def open_position(
        self,
        db: Session,
        *,
        order_id: int | None,
        ticker: str,
        strategy_id: str,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        quantity: float,
    ) -> Position:
        row = Position(
            order_id=order_id,
            ticker=ticker,
            strategy_id=strategy_id,
            state="OPEN",
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            trailing_stop_price=None,
            highest_price=entry_price,
            quantity=quantity,
            remaining_quantity=quantity,
            entry_time=datetime.now(timezone.utc),
            closed_time=None,
            close_reason=None,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_open_positions(self, db: Session) -> list[Position]:
        return db.scalars(select(Position).where(Position.state != "CLOSED")).all()

    def list_positions(
        self,
        db: Session,
        *,
        state: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Position]:
        stmt = select(Position)
        if state is not None and state.strip():
            stmt = stmt.where(Position.state == state)
        rows = db.scalars(
            stmt.order_by(Position.updated_at.desc()).offset(max(offset, 0)).limit(limit)
        ).all()
        return list(rows)

    def count_positions(self, db: Session, *, state: str | None = None) -> int:
        stmt = select(Position.id)
        if state is not None and state.strip():
            stmt = stmt.where(Position.state == state)
        return len(db.scalars(stmt).all())

    def mark_position_closed(self, db: Session, position_id: int, reason: str) -> Position:
        row = db.get(Position, position_id)
        if row is None:
            raise KeyError(f"position not found: {position_id}")
        row.state = "CLOSED"
        row.remaining_quantity = 0.0
        row.closed_time = datetime.now(timezone.utc)
        row.close_reason = reason
        db.commit()
        db.refresh(row)
        return row

    def apply_transition(self, db: Session, position_id: int, transition: Transition) -> Position:
        row = db.get(Position, position_id)
        if row is None:
            raise KeyError(f"position not found: {position_id}")

        row.state = transition.new_state
        row.highest_price = transition.new_highest
        row.trailing_stop_price = transition.new_trailing_stop
        if transition.close_qty > 0:
            row.remaining_quantity = max(row.remaining_quantity - transition.close_qty, 0.0)
        if transition.new_state == "CLOSED":
            row.closed_time = datetime.now(timezone.utc)
            if transition.reason:
                row.close_reason = transition.reason

        db.commit()
        db.refresh(row)
        return row
