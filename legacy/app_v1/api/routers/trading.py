from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.order import Order
from app.db.models.position import Position
from app.db.session import get_db
from app.services.performance_service import PerformanceService

router = APIRouter(prefix="/trading", tags=["trading"])


@router.get("/positions")
def list_positions(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Position).order_by(Position.id.desc()).limit(100)).all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "strategy_id": r.strategy_id,
            "state": r.state,
            "entry_price": r.entry_price,
            "remaining_quantity": r.remaining_quantity,
            "close_reason": r.close_reason,
        }
        for r in rows
    ]


@router.get("/orders")
def list_orders(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Order).order_by(Order.id.desc()).limit(100)).all()
    return [
        {
            "id": r.id,
            "ticker": r.ticker,
            "strategy_id": r.strategy_id,
            "status": r.status,
            "order_type": r.order_type,
            "price": r.price,
            "qty": r.quantity,
            "filled": r.filled_quantity,
            "reason": r.reason,
        }
        for r in rows
    ]


@router.get("/paper-report")
def paper_report(db: Session = Depends(get_db)) -> dict:
    return PerformanceService().paper_report(db)
