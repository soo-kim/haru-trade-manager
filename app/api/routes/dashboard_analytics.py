from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError


def create_dashboard_analytics_router(
    *,
    require_dashboard_session: Callable[..., dict[str, object]],
    parse_datetime: Callable[[str | None], object],
    performance_service,
    strategy_performance_service,
    session_factory,
    ordering_repo,
    candle_repo,
    position_to_dict: Callable[[object], dict[str, object]],
    auth_audit_service,
) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard/performance/snapshots")
    def dashboard_snapshots(
        page: int = 1,
        page_size: int = 100,
        start: str | None = None,
        end: str | None = None,
        snapshot_type: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 1000))
        offset = (safe_page - 1) * safe_size
        result = performance_service.list_snapshot_records(
            start=parse_datetime(start),
            end=parse_datetime(end),
            snapshot_type=snapshot_type,
            offset=offset,
            limit=safe_size,
        )
        total = int(result.get("meta", {}).get("total", 0)) if result.get("ok") else 0
        total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
        return {
            "ok": bool(result.get("ok")),
            "data": {"items": result.get("items", [])},
            "meta": {
                "total": total,
                "page": safe_page,
                "page_size": safe_size,
                "total_pages": total_pages,
                "error": result.get("error"),
            },
        }

    @router.get("/dashboard/performance/equity-curve")
    def dashboard_equity_curve(
        start: str | None = None,
        end: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        result = performance_service.equity_curve(start=parse_datetime(start), end=parse_datetime(end))
        return {
            "ok": bool(result.get("ok")),
            "data": {"items": result.get("items", [])},
            "meta": result.get("meta", {}),
            "error": result.get("error"),
        }

    @router.get("/dashboard/strategy-performance")
    def dashboard_strategy_performance(
        page: int = 1,
        page_size: int = 50,
        start: str | None = None,
        end: str | None = None,
        strategy_id: str | None = None,
        q: str | None = None,
        min_trades: int = 0,
        sort_by: str = "total_pnl",
        sort_order: str = "desc",
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 1000))
        offset = (safe_page - 1) * safe_size
        result = strategy_performance_service.report(
            start=parse_datetime(start),
            end=parse_datetime(end),
            strategy_id=strategy_id,
            strategy_query=q,
            offset=offset,
            limit=safe_size,
            min_trades=max(min_trades, 0),
            sort_by=sort_by,
            sort_order=sort_order,
        )
        total = int(result.get("meta", {}).get("total", 0)) if result.get("ok") else 0
        total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
        return {
            "ok": bool(result.get("ok")),
            "data": {"items": result.get("items", [])},
            "meta": {
                "total": total,
                "page": safe_page,
                "page_size": safe_size,
                "total_pages": total_pages,
                "error": result.get("error"),
            },
        }

    @router.get("/dashboard/positions")
    def dashboard_positions(
        page: int = 1,
        page_size: int = 50,
        state: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 500))
        offset = (safe_page - 1) * safe_size
        try:
            with session_factory() as db:
                total = ordering_repo.count_positions(db, state=state)
                rows = ordering_repo.list_positions(db, state=state, offset=offset, limit=safe_size)
                latest_prices: dict[str, float | None] = {}

                def _price_for(ticker: str) -> float | None:
                    if ticker not in latest_prices:
                        latest_prices[ticker] = candle_repo.get_latest_close(db, ticker=ticker)
                    return latest_prices[ticker]

            total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
            return {
                "ok": True,
                "data": {"items": [position_to_dict(x, current_price=_price_for(getattr(x, "ticker"))) for x in rows]},
                "meta": {"total": total, "page": safe_page, "page_size": safe_size, "total_pages": total_pages},
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "data": {"items": []}, "meta": {"error": str(exc)}}

    @router.get("/dashboard/auth/audit")
    def dashboard_auth_audit(
        page: int = 1,
        page_size: int = 100,
        event_type: str | None = None,
        ip: str | None = None,
        ok: bool | None = None,
        start: str | None = None,
        end: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 1000))
        offset = (safe_page - 1) * safe_size
        result = auth_audit_service.list_events(
            event_type=event_type,
            ip=ip,
            ok=ok,
            start=parse_datetime(start),
            end=parse_datetime(end),
            offset=offset,
            limit=safe_size,
        )
        total = int(result.get("meta", {}).get("total", 0)) if result.get("ok") else 0
        total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
        return {
            "ok": bool(result.get("ok")),
            "data": {"items": result.get("items", [])},
            "meta": {
                "total": total,
                "page": safe_page,
                "page_size": safe_size,
                "total_pages": total_pages,
                "error": result.get("error"),
            },
        }

    @router.get("/dashboard/auth/metrics")
    def dashboard_auth_metrics(
        last_hours: int = 24,
        ip: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        result = auth_audit_service.metrics(last_hours=last_hours, ip=ip)
        return {
            "ok": bool(result.get("ok")),
            "data": result.get("data", {}),
            "meta": result.get("meta", {}),
            "error": result.get("error"),
        }

    return router
