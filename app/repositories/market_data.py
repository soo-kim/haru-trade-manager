from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.market_data import CandleCollectionState


class CandleCollectionStateRepository:
    def get_state(self, db: Session, *, ticker: str, timeframe: str) -> CandleCollectionState | None:
        return db.get(CandleCollectionState, {"ticker": ticker, "timeframe": timeframe})

    def record_success(
        self,
        db: Session,
        *,
        ticker: str,
        timeframe: str,
        first_candle_time: datetime | None,
        last_candle_time: datetime | None,
        row_count: int,
        source: str,
        collected_at: datetime,
    ) -> CandleCollectionState:
        row = self.get_state(db, ticker=ticker, timeframe=timeframe)
        if row is None:
            row = CandleCollectionState(ticker=ticker, timeframe=timeframe)
            db.add(row)
        row.first_candle_time = first_candle_time
        row.last_candle_time = last_candle_time
        row.row_count = max(int(row_count), 0)
        row.last_success_at = collected_at
        row.last_error = None
        row.consecutive_error_count = 0
        row.source = source
        row.updated_at = collected_at
        db.commit()
        db.refresh(row)
        return row

    def record_failure(
        self,
        db: Session,
        *,
        ticker: str,
        timeframe: str,
        error: str,
        source: str,
        failed_at: datetime,
    ) -> CandleCollectionState:
        row = self.get_state(db, ticker=ticker, timeframe=timeframe)
        if row is None:
            row = CandleCollectionState(ticker=ticker, timeframe=timeframe, row_count=0)
            db.add(row)
        row.last_error_at = failed_at
        row.last_error = error[:2000]
        row.consecutive_error_count = int(row.consecutive_error_count or 0) + 1
        row.source = source
        row.updated_at = failed_at
        db.commit()
        db.refresh(row)
        return row

    def list_states(
        self,
        db: Session,
        *,
        timeframe: str | None = None,
        ticker: str | None = None,
        limit: int = 20_000,
    ) -> list[CandleCollectionState]:
        stmt = select(CandleCollectionState)
        if timeframe is not None and timeframe.strip():
            stmt = stmt.where(CandleCollectionState.timeframe == timeframe)
        if ticker is not None and ticker.strip():
            stmt = stmt.where(CandleCollectionState.ticker == ticker)
        rows = db.scalars(
            stmt.order_by(CandleCollectionState.timeframe.asc(), CandleCollectionState.ticker.asc()).limit(limit)
        ).all()
        return list(rows)
