from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.paper import PaperOrder, PaperTrade


class PaperRepository:
    def create_order(
        self,
        db: Session,
        *,
        ticker: str,
        side: str,
        order_type: str,
        price: float,
        quantity: float,
        status: str = "filled",
    ) -> PaperOrder:
        row = PaperOrder(
            ticker=ticker,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            status=status,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def create_trade(
        self,
        db: Session,
        *,
        ticker: str,
        strategy_id: str = "default",
        side: str,
        entry_price: float,
        exit_price: float | None,
        quantity: float,
        pnl: float | None,
        created_at: datetime | None = None,
    ) -> PaperTrade:
        row = PaperTrade(
            ticker=ticker,
            strategy_id=strategy_id,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            pnl=pnl,
            created_at=created_at or datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def list_trades(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        ticker: str | None = None,
        strategy_id: str | None = None,
        side: str | None = None,
        offset: int = 0,
        limit: int = 10000,
        desc: bool = False,
    ) -> list[PaperTrade]:
        stmt = select(PaperTrade)
        if start is not None:
            stmt = stmt.where(PaperTrade.created_at >= start)
        if end is not None:
            stmt = stmt.where(PaperTrade.created_at <= end)
        if ticker is not None and ticker.strip():
            stmt = stmt.where(PaperTrade.ticker == ticker.strip())
        if strategy_id is not None and strategy_id.strip():
            stmt = stmt.where(PaperTrade.strategy_id == strategy_id)
        if side is not None and side.strip():
            stmt = stmt.where(PaperTrade.side == side.strip())
        order_col = PaperTrade.created_at.desc() if desc else PaperTrade.created_at.asc()
        return db.scalars(stmt.order_by(order_col).offset(max(offset, 0)).limit(limit)).all()

    def count_trades(
        self,
        db: Session,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        ticker: str | None = None,
        strategy_id: str | None = None,
        side: str | None = None,
    ) -> int:
        stmt = select(PaperTrade.id)
        if start is not None:
            stmt = stmt.where(PaperTrade.created_at >= start)
        if end is not None:
            stmt = stmt.where(PaperTrade.created_at <= end)
        if ticker is not None and ticker.strip():
            stmt = stmt.where(PaperTrade.ticker == ticker.strip())
        if strategy_id is not None and strategy_id.strip():
            stmt = stmt.where(PaperTrade.strategy_id == strategy_id)
        if side is not None and side.strip():
            stmt = stmt.where(PaperTrade.side == side.strip())
        return len(db.scalars(stmt).all())

    def list_orders(self, db: Session, *, limit: int = 10000) -> list[PaperOrder]:
        return db.scalars(select(PaperOrder).order_by(PaperOrder.created_at.asc()).limit(limit)).all()
