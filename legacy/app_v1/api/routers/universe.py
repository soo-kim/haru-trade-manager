from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config_manager import ConfigManager
from app.db.models.universe import Symbol
from app.db.session import get_db
from app.services.universe_service import UniverseService

router = APIRouter(prefix="/universe", tags=["universe"])
manager = ConfigManager.get_instance()
service = UniverseService()


class SymbolUpsertRequest(BaseModel):
    ticker: str
    name: str
    market: str = "KOSPI"


@router.get("")
def list_universe(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Symbol).order_by(Symbol.ticker)).all()
    return [
        {
            "ticker": s.ticker,
            "name": s.name,
            "market": s.market,
            "in_universe": s.in_universe,
            "is_active": s.is_active,
            "is_blocked": s.is_blocked,
            "status": s.status,
        }
        for s in rows
    ]


@router.post("/refresh-active")
def refresh_active_universe(db: Session = Depends(get_db)) -> dict[str, int]:
    threshold = float(manager.get("liquidity_threshold"))
    changed = service.refresh_active_universe(db, threshold)
    return {"changed": changed}


@router.post("/upsert")
def upsert_symbol(request: SymbolUpsertRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.get(Symbol, request.ticker)
    if row is None:
        row = Symbol(
            ticker=request.ticker,
            name=request.name,
            market=request.market,
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        db.add(row)
    else:
        row.name = request.name
        row.market = request.market
    db.commit()
    return {"ticker": request.ticker, "status": "ok"}


@router.post("/block/{ticker}")
def block_symbol(ticker: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.get(Symbol, ticker)
    if row is None:
        return {"ticker": ticker, "status": "not_found"}
    row.is_blocked = True
    row.is_active = False
    db.commit()
    return {"ticker": ticker, "status": "blocked"}


@router.post("/unblock/{ticker}")
def unblock_symbol(ticker: str, db: Session = Depends(get_db)) -> dict[str, str]:
    row = db.get(Symbol, ticker)
    if row is None:
        return {"ticker": ticker, "status": "not_found"}
    row.is_blocked = False
    db.commit()
    return {"ticker": ticker, "status": "unblocked"}
