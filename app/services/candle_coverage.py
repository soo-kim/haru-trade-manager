from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.models.candle import Candle
from app.db.models.market_data import CandleCollectionState
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository
from app.repositories.universe import UniverseRepository


class CandleCoverageService:
    def __init__(
        self,
        *,
        session_factory,
        universe_repo: UniverseRepository | None = None,
        candle_repo: CandleRepository | None = None,
        state_repo: CandleCollectionStateRepository | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.universe_repo = universe_repo or UniverseRepository()
        self.candle_repo = candle_repo or CandleRepository()
        self.state_repo = state_repo or CandleCollectionStateRepository()
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def coverage(self, *, timeframes: tuple[str, ...], stale_after: datetime | None = None) -> dict[str, Any]:
        with self.session_factory() as db:
            universe_tickers = list(self.universe_repo.list_universe_tickers(db))
            universe_set = set(universe_tickers)
            universe_count = len(universe_tickers)
            by_timeframe: dict[str, Any] = {}
            for timeframe in timeframes:
                rows = db.execute(
                    select(
                        Candle.ticker.label("ticker"),
                        func.min(Candle.candle_time).label("first_candle_time"),
                        func.max(Candle.candle_time).label("last_candle_time"),
                        func.count(Candle.id).label("row_count"),
                    )
                    .where(Candle.timeframe == timeframe, Candle.ticker.in_(universe_tickers) if universe_tickers else False)
                    .group_by(Candle.ticker)
                ).all()
                row_by_ticker = {r.ticker: r for r in rows}
                states = {
                    s.ticker: s
                    for s in db.scalars(
                        select(CandleCollectionState).where(
                            CandleCollectionState.timeframe == timeframe,
                            CandleCollectionState.ticker.in_(universe_tickers) if universe_tickers else False,
                        )
                    ).all()
                }
                missing = sorted(universe_set - set(row_by_ticker))
                stale = [
                    ticker
                    for ticker, row in row_by_ticker.items()
                    if stale_after is not None and row.last_candle_time is not None and row.last_candle_time < stale_after
                ]
                failed = [ticker for ticker, s in states.items() if s.consecutive_error_count > 0 or s.last_error]
                latest = max((r.last_candle_time for r in rows if r.last_candle_time is not None), default=None)
                earliest = min((r.first_candle_time for r in rows if r.first_candle_time is not None), default=None)
                by_timeframe[timeframe] = {
                    "ticker_count": len(row_by_ticker),
                    "missing_count": len(missing),
                    "missing_tickers": missing[:100],
                    "stale_count": len(stale),
                    "stale_tickers": sorted(stale)[:100],
                    "failed_state_count": len(failed),
                    "failed_tickers": sorted(failed)[:100],
                    "backtest_ready_count": len(set(row_by_ticker) - set(stale) - set(failed)),
                    "row_count": int(sum(int(r.row_count or 0) for r in rows)),
                    "earliest_candle_time": earliest.isoformat() if earliest else None,
                    "latest_candle_time": latest.isoformat() if latest else None,
                }
            return {
                "generated_at": self.now_fn().isoformat(),
                "universe_count": universe_count,
                "timeframes": by_timeframe,
            }

    def states(self, *, timeframe: str | None = None, ticker: str | None = None) -> list[dict[str, Any]]:
        with self.session_factory() as db:
            rows = self.state_repo.list_states(db, timeframe=timeframe, ticker=ticker)
            return [
                {
                    "ticker": row.ticker,
                    "timeframe": row.timeframe,
                    "first_candle_time": row.first_candle_time.isoformat() if row.first_candle_time else None,
                    "last_candle_time": row.last_candle_time.isoformat() if row.last_candle_time else None,
                    "row_count": row.row_count,
                    "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                    "last_error_at": row.last_error_at.isoformat() if row.last_error_at else None,
                    "last_error": row.last_error,
                    "consecutive_error_count": row.consecutive_error_count,
                    "source": row.source,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in rows
            ]
