from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.candle import Candle as CandleRow


class CandleRepository:
    def upsert_incremental(
        self,
        db: Session,
        *,
        ticker: str,
        timeframe: str,
        candle_time: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: float,
    ) -> CandleRow:
        existing = db.scalar(
            select(CandleRow).where(
                CandleRow.ticker == ticker,
                CandleRow.timeframe == timeframe,
                CandleRow.candle_time == candle_time,
            )
        )
        if existing is not None:
            existing.open = open_price
            existing.high = high
            existing.low = low
            existing.close = close
            existing.volume = volume
            db.commit()
            return existing

        row = CandleRow(
            ticker=ticker,
            timeframe=timeframe,
            candle_time=candle_time,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
        db.add(row)
        db.commit()
        return row

    def get_last_candle_time(self, db: Session, *, ticker: str, timeframe: str) -> datetime | None:
        return db.scalar(
            select(CandleRow.candle_time)
            .where(CandleRow.ticker == ticker, CandleRow.timeframe == timeframe)
            .order_by(CandleRow.candle_time.desc())
            .limit(1)
        )

    def list_recent(self, db: Session, *, ticker: str, timeframe: str, limit: int = 240) -> list[CandleRow]:
        rows = db.scalars(
            select(CandleRow)
            .where(CandleRow.ticker == ticker, CandleRow.timeframe == timeframe)
            .order_by(CandleRow.candle_time.desc())
            .limit(limit)
        ).all()
        rows.reverse()
        return rows

    def list_range(
        self,
        db: Session,
        *,
        ticker: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        offset: int = 0,
        limit: int = 20_000,
    ) -> list[CandleRow]:
        stmt = select(CandleRow).where(CandleRow.ticker == ticker, CandleRow.timeframe == timeframe)
        if start is not None:
            stmt = stmt.where(CandleRow.candle_time >= start)
        if end is not None:
            stmt = stmt.where(CandleRow.candle_time <= end)
        rows = db.scalars(
            stmt.order_by(CandleRow.candle_time.asc()).offset(max(offset, 0)).limit(max(1, limit))
        ).all()
        return list(rows)

    def list_tickers(self, db: Session) -> list[str]:
        rows = db.execute(select(CandleRow.ticker).distinct().order_by(CandleRow.ticker.asc())).all()
        return [x[0] for x in rows]

    def get_latest_close(self, db: Session, *, ticker: str) -> float | None:
        return db.scalar(
            select(CandleRow.close).where(CandleRow.ticker == ticker).order_by(CandleRow.candle_time.desc()).limit(1)
        )

    def upsert_batch(
        self,
        db: Session,
        *,
        ticker: str,
        timeframe: str,
        candles: list[dict[str, float | datetime]],
    ) -> tuple[int, int]:
        if not candles:
            return (0, 0)

        deduped_by_time: dict[datetime, dict[str, float | datetime]] = {}
        for item in candles:
            candle_time = item.get("candle_time")
            if isinstance(candle_time, datetime):
                deduped_by_time[candle_time] = item
        times = list(deduped_by_time.keys())
        existing_rows = db.scalars(
            select(CandleRow).where(
                CandleRow.ticker == ticker,
                CandleRow.timeframe == timeframe,
                CandleRow.candle_time.in_(times),
            )
        ).all()
        existing_map = {x.candle_time: x for x in existing_rows}

        inserted = 0
        updated = 0
        for candle_time, item in deduped_by_time.items():
            row = existing_map.get(candle_time)
            if row is None:
                db.add(
                    CandleRow(
                        ticker=ticker,
                        timeframe=timeframe,
                        candle_time=candle_time,
                        open=float(item["open"]),
                        high=float(item["high"]),
                        low=float(item["low"]),
                        close=float(item["close"]),
                        volume=float(item["volume"]),
                    )
                )
                inserted += 1
                continue
            row.open = float(item["open"])
            row.high = float(item["high"])
            row.low = float(item["low"])
            row.close = float(item["close"])
            row.volume = float(item["volume"])
            updated += 1

        db.commit()
        return (inserted, updated)
