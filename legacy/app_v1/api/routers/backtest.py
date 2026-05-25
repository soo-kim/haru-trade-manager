from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.backtest.engine import BacktestEngine, BacktestSignal, CandleBar
from app.db.models.candle import Candle
from app.db.session import get_db

router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    ticker: str
    timeframe: str = "5m"
    signal_index: int
    side: str = "buy"


@router.post("/entry-preview")
def backtest_entry_preview(request: BacktestRequest, db: Session = Depends(get_db)) -> dict:
    candles = db.scalars(
        select(Candle)
        .where(Candle.ticker == request.ticker, Candle.timeframe == request.timeframe)
        .order_by(Candle.candle_time)
    ).all()
    if len(candles) < request.signal_index + 2:
        raise HTTPException(status_code=400, detail="not enough candles for N+1 entry")

    bars = [CandleBar(open=c.open, high=c.high, low=c.low, close=c.close) for c in candles]
    engine = BacktestEngine(
        fee_buy_pct=0.015,
        fee_sell_pct=0.015,
        tax_sell_pct=0.18,
        slippage_pct=0.05,
    )
    signal = BacktestSignal(index=request.signal_index, side=request.side)
    entry = engine.entry_price_n_plus_one_open(bars, signal)
    return {
        "ticker": request.ticker,
        "signal_index": request.signal_index,
        "entry_price": entry,
        "round_trip_cost_pct": engine.round_trip_cost_pct(),
    }
