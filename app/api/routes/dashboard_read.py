from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError


def create_dashboard_read_router(
    *,
    require_dashboard_session: Callable[..., dict[str, object]],
    runtime_snapshot_provider: Callable[[], dict[str, object]],
    performance_service,
    paper_report_service,
    live_connectivity_checker,
    startup_bootstrap_status: dict[str, object],
    backtest_service,
    session_factory,
    universe_repo,
    symbol_to_dict: Callable[[object], dict[str, object]],
    candle_row_model,
    supported_timeframes: tuple[str, ...],
) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard/summary")
    async def dashboard_summary(_: dict[str, object] = Depends(require_dashboard_session)) -> dict[str, object]:
        runtime = runtime_snapshot_provider()
        performance = performance_service.twr_report()
        paper = paper_report_service.build_report()
        connectivity = await live_connectivity_checker()
        return {
            "ok": True,
            "data": {
                "runtime": runtime,
                "performance": performance,
                "paper_report": paper,
                "api_connectivity": connectivity,
                "startup_bootstrap": startup_bootstrap_status,
            },
            "meta": {"generated_at": datetime.now(timezone.utc).isoformat()},
        }

    @router.get("/dashboard/backtests")
    async def dashboard_backtests(
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 200))
        offset = (safe_page - 1) * safe_size
        total = await backtest_service.count_jobs(status=status)
        items = await backtest_service.list_jobs(limit=safe_size, offset=offset, status=status)
        total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
        return {
            "ok": True,
            "data": {"items": items},
            "meta": {
                "total": total,
                "page": safe_page,
                "page_size": safe_size,
                "total_pages": total_pages,
                "status": status,
            },
        }

    @router.get("/dashboard/backtests/candle-range")
    def dashboard_backtests_candle_range(
        ticker: str,
        timeframe: str = "5m",
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        clean_ticker = ticker.strip()
        clean_timeframe = timeframe.strip()
        if not clean_ticker:
            return {"ok": False, "error": "ticker is required"}
        if clean_timeframe not in supported_timeframes:
            return {"ok": False, "error": f"unsupported timeframe: {clean_timeframe}"}
        try:
            with session_factory() as db:
                row = db.execute(
                    select(
                        func.min(candle_row_model.candle_time).label("min_time"),
                        func.max(candle_row_model.candle_time).label("max_time"),
                        func.count(candle_row_model.id).label("count_rows"),
                    ).where(candle_row_model.ticker == clean_ticker, candle_row_model.timeframe == clean_timeframe)
                ).one()
            count_rows = int(row.count_rows or 0)
            if count_rows == 0:
                return {
                    "ok": True,
                    "data": {"ticker": clean_ticker, "timeframe": clean_timeframe, "count": 0, "start": None, "end": None},
                }
            return {
                "ok": True,
                "data": {
                    "ticker": clean_ticker,
                    "timeframe": clean_timeframe,
                    "count": count_rows,
                    "start": row.min_time.isoformat() if row.min_time is not None else None,
                    "end": row.max_time.isoformat() if row.max_time is not None else None,
                },
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc)}

    @router.get("/dashboard/universe")
    def dashboard_universe(
        page: int = 1,
        page_size: int = 50,
        runtime_only: bool = False,
        in_universe: bool | None = True,
        market: str | None = None,
        is_active: bool | None = None,
        is_blocked: bool | None = None,
        status: str | None = None,
        q: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 500))
        offset = (safe_page - 1) * safe_size
        try:
            with session_factory() as db:
                total = universe_repo.count_symbols(
                    db,
                    runtime_only=runtime_only,
                    in_universe=in_universe,
                    market=market,
                    is_active=is_active,
                    is_blocked=is_blocked,
                    status=status,
                    ticker_query=q,
                )
                rows = universe_repo.list_symbols(
                    db,
                    runtime_only=runtime_only,
                    in_universe=in_universe,
                    market=market,
                    is_active=is_active,
                    is_blocked=is_blocked,
                    status=status,
                    ticker_query=q,
                    offset=offset,
                    limit=safe_size,
                )
            total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
            return {
                "ok": True,
                "data": {"items": [symbol_to_dict(x) for x in rows]},
                "meta": {"total": total, "page": safe_page, "page_size": safe_size, "total_pages": total_pages},
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "data": {"items": []}, "meta": {"error": str(exc)}}

    @router.post("/dashboard/universe/{ticker}/block")
    def dashboard_universe_block(
        ticker: str,
        blocked: bool = True,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        try:
            with session_factory() as db:
                row = universe_repo.set_blocked(db, ticker=ticker, blocked=blocked)
            return {"ok": True, "item": symbol_to_dict(row)}
        except SQLAlchemyError as exc:
            return {"ok": False, "error": str(exc), "ticker": ticker}
        except KeyError:
            return {"ok": False, "error": "symbol_not_found", "ticker": ticker}

    return router
