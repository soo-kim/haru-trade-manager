from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.universe import Symbol
from app.domain.universe_status import UniverseStatus


class UniverseRepository:
    def upsert_symbol(
        self,
        db: Session,
        *,
        ticker: str,
        name: str,
        market: str,
        in_universe: bool = True,
        is_active: bool = False,
        is_blocked: bool = False,
        status: str = UniverseStatus.NORMAL.value,
    ) -> Symbol:
        row = db.get(Symbol, ticker)
        if row is None:
            row = Symbol(
                ticker=ticker,
                name=name,
                market=market,
                in_universe=in_universe,
                is_active=is_active,
                is_blocked=is_blocked,
                status=status,
            )
            db.add(row)
        else:
            row.name = name
            row.market = market
            row.in_universe = in_universe
            row.is_active = is_active
            row.is_blocked = is_blocked
            row.status = status

        db.commit()
        db.refresh(row)
        return row

    def list_trading_tickers(self, db: Session, *, limit: int = 500) -> list[str]:
        rows = db.scalars(
            select(Symbol.ticker)
            .where(
                Symbol.in_universe.is_(True),
                Symbol.is_active.is_(True),
                Symbol.is_blocked.is_(False),
                Symbol.status != UniverseStatus.HALTED.value,
            )
            .order_by(Symbol.ticker.asc())
            .limit(limit)
        ).all()
        return list(rows)

    def list_tracking_tickers(self, db: Session, *, limit: int = 500) -> list[str]:
        rows = db.scalars(
            select(Symbol.ticker)
            .where(
                Symbol.in_universe.is_(True),
                Symbol.is_active.is_(True),
            )
            .order_by(Symbol.ticker.asc())
            .limit(limit)
        ).all()
        return list(rows)

    def list_universe_tickers(self, db: Session, *, limit: int = 20_000) -> list[str]:
        rows = db.scalars(
            select(Symbol.ticker)
            .where(Symbol.in_universe.is_(True))
            .order_by(Symbol.ticker.asc())
            .limit(limit)
        ).all()
        return list(rows)

    def list_runtime_tickers(self, db: Session, *, limit: int = 500) -> list[str]:
        # 하위호환: 기존 runtime_tickers는 주문 가능(unblocked) 기준을 유지한다.
        return self.list_trading_tickers(db, limit=limit)

    def list_symbols(
        self,
        db: Session,
        *,
        runtime_only: bool = False,
        in_universe: bool | None = None,
        market: str | None = None,
        is_active: bool | None = None,
        is_blocked: bool | None = None,
        status: str | None = None,
        ticker_query: str | None = None,
        offset: int = 0,
        limit: int = 1000,
    ) -> list[Symbol]:
        stmt = select(Symbol)
        if runtime_only:
            stmt = stmt.where(
                Symbol.in_universe.is_(True),
                Symbol.is_active.is_(True),
                Symbol.is_blocked.is_(False),
                Symbol.status != UniverseStatus.HALTED.value,
            )
        if in_universe is not None:
            stmt = stmt.where(Symbol.in_universe.is_(in_universe))
        if market is not None and market.strip():
            stmt = stmt.where(Symbol.market == market)
        if is_active is not None:
            stmt = stmt.where(Symbol.is_active.is_(is_active))
        if is_blocked is not None:
            stmt = stmt.where(Symbol.is_blocked.is_(is_blocked))
        if status is not None and status.strip():
            stmt = stmt.where(Symbol.status == status)
        if ticker_query is not None and ticker_query.strip():
            pattern = f"%{ticker_query.strip()}%"
            stmt = stmt.where(Symbol.ticker.ilike(pattern) | Symbol.name.ilike(pattern))
        rows = db.scalars(stmt.order_by(Symbol.ticker.asc()).offset(max(offset, 0)).limit(limit)).all()
        return list(rows)

    def set_blocked(self, db: Session, *, ticker: str, blocked: bool) -> Symbol:
        row = db.get(Symbol, ticker)
        if row is None:
            raise KeyError(f"symbol not found: {ticker}")
        row.is_blocked = blocked
        db.commit()
        db.refresh(row)
        return row

    def count_symbols(
        self,
        db: Session,
        *,
        runtime_only: bool = False,
        in_universe: bool | None = None,
        market: str | None = None,
        is_active: bool | None = None,
        is_blocked: bool | None = None,
        status: str | None = None,
        ticker_query: str | None = None,
    ) -> int:
        stmt = select(Symbol.ticker)
        if runtime_only:
            stmt = stmt.where(
                Symbol.in_universe.is_(True),
                Symbol.is_active.is_(True),
                Symbol.is_blocked.is_(False),
                Symbol.status != UniverseStatus.HALTED.value,
            )
        if in_universe is not None:
            stmt = stmt.where(Symbol.in_universe.is_(in_universe))
        if market is not None and market.strip():
            stmt = stmt.where(Symbol.market == market)
        if is_active is not None:
            stmt = stmt.where(Symbol.is_active.is_(is_active))
        if is_blocked is not None:
            stmt = stmt.where(Symbol.is_blocked.is_(is_blocked))
        if status is not None and status.strip():
            stmt = stmt.where(Symbol.status == status)
        if ticker_query is not None and ticker_query.strip():
            pattern = f"%{ticker_query.strip()}%"
            stmt = stmt.where(Symbol.ticker.ilike(pattern) | Symbol.name.ilike(pattern))
        return len(db.scalars(stmt).all())
