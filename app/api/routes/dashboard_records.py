from __future__ import annotations

import csv
import io
from collections.abc import Callable

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError


class DashboardConfigSetRequest(BaseModel):
    key: str
    value: str


def create_dashboard_records_router(
    *,
    require_dashboard_session: Callable[..., dict[str, object]],
    config_service,
    dashboard_setting_item: Callable[..., dict[str, object]],
    session_factory,
    config_repo,
    config_history_to_dict: Callable[[object], dict[str, object]],
    paper_repo,
    ordering_repo,
    parse_datetime: Callable[[str | None], object],
    find_nearest_closed_position: Callable[..., object | None],
    trade_to_dict: Callable[..., dict[str, object]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/dashboard/settings")
    def dashboard_settings(_: dict[str, object] = Depends(require_dashboard_session)) -> dict[str, object]:
        values = config_service.get_all()
        webui_only_keys = {
            "atr_period",
            "stop_atr_mult",
            "tp_atr_mult",
            "trail_atr_mult",
            "margin_close_priority",
        }
        return {
            "ok": True,
            "data": {
                "items": [
                    dashboard_setting_item(
                        key=key,
                        value=value,
                        webui_only_keys=webui_only_keys,
                    )
                    for key, value in sorted(values.items(), key=lambda x: x[0])
                ]
            },
            "meta": {"total": len(values)},
        }

    @router.post("/dashboard/settings")
    def dashboard_set_settings(
        req: DashboardConfigSetRequest,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        try:
            config_service.set(key=req.key, value=req.value, changed_by="webui")
        except (KeyError, ValueError) as exc:
            return {"ok": False, "error": str(exc), "key": req.key}
        return {"ok": True, "key": req.key, "value": req.value}

    @router.get("/dashboard/settings/history")
    def dashboard_settings_history(
        page: int = 1,
        page_size: int = 100,
        key: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 1000))
        offset = (safe_page - 1) * safe_size
        try:
            with session_factory() as db:
                total = config_repo.count_history(db, key=key)
                rows = config_repo.list_history(db, key=key, offset=offset, limit=safe_size)
            total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
            return {
                "ok": True,
                "data": {"items": [config_history_to_dict(x) for x in rows]},
                "meta": {"total": total, "page": safe_page, "page_size": safe_size, "total_pages": total_pages},
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "data": {"items": []}, "meta": {"error": str(exc)}}

    @router.get("/dashboard/trades")
    def dashboard_trades(
        page: int = 1,
        page_size: int = 50,
        start: str | None = None,
        end: str | None = None,
        ticker: str | None = None,
        strategy_id: str | None = None,
        side: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        safe_page = max(page, 1)
        safe_size = max(1, min(page_size, 1000))
        offset = (safe_page - 1) * safe_size
        try:
            with session_factory() as db:
                total = paper_repo.count_trades(
                    db,
                    start=parse_datetime(start),
                    end=parse_datetime(end),
                    ticker=ticker,
                    strategy_id=strategy_id,
                    side=side,
                )
                rows = paper_repo.list_trades(
                    db,
                    start=parse_datetime(start),
                    end=parse_datetime(end),
                    ticker=ticker,
                    strategy_id=strategy_id,
                    side=side,
                    offset=offset,
                    limit=safe_size,
                    desc=True,
                )
                closed_positions = ordering_repo.list_positions(db, state="CLOSED", offset=0, limit=20_000)
                positions_by_key: dict[tuple[str, str], list[object]] = {}
                for pos in closed_positions:
                    key = (str(getattr(pos, "ticker")), str(getattr(pos, "strategy_id")))
                    positions_by_key.setdefault(key, []).append(pos)
                for bucket in positions_by_key.values():
                    bucket.sort(
                        key=lambda x: (
                            getattr(x, "closed_time").timestamp() if getattr(x, "closed_time") is not None else 0.0
                        )
                    )
            total_pages = (total + safe_size - 1) // safe_size if total > 0 else 0
            items = []
            for trade in rows:
                key = (str(getattr(trade, "ticker")), str(getattr(trade, "strategy_id")))
                matched = find_nearest_closed_position(trade=trade, candidates=positions_by_key.get(key, []))
                items.append(trade_to_dict(trade, closed_position=matched))
            return {
                "ok": True,
                "data": {"items": items},
                "meta": {"total": total, "page": safe_page, "page_size": safe_size, "total_pages": total_pages},
            }
        except SQLAlchemyError as exc:
            return {"ok": False, "data": {"items": []}, "meta": {"error": str(exc)}}

    @router.get("/dashboard/trades/export.csv")
    def dashboard_trades_export_csv(
        start: str | None = None,
        end: str | None = None,
        ticker: str | None = None,
        strategy_id: str | None = None,
        side: str | None = None,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> Response:
        with session_factory() as db:
            rows = paper_repo.list_trades(
                db,
                start=parse_datetime(start),
                end=parse_datetime(end),
                ticker=ticker,
                strategy_id=strategy_id,
                side=side,
                limit=50_000,
                desc=True,
            )
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "id",
                "ticker",
                "strategy_id",
                "side",
                "entry_price",
                "exit_price",
                "quantity",
                "pnl",
                "pnl_pct",
                "entry_time",
                "exit_time",
                "holding_minutes",
                "close_reason",
            ]
        )
        for row in rows:
            item = trade_to_dict(row)
            writer.writerow(
                [
                    item["id"],
                    item["ticker"],
                    item["strategy_id"],
                    item["side"],
                    item["entry_price"],
                    item["exit_price"],
                    item["quantity"],
                    item["pnl"],
                    item["pnl_pct"],
                    item["entry_time"],
                    item["exit_time"],
                    item["holding_minutes"],
                    item["close_reason"],
                ]
            )
        content = buf.getvalue()
        headers = {"Content-Disposition": 'attachment; filename="trades.csv"'}
        return Response(content=content, media_type="text/csv; charset=utf-8", headers=headers)

    return router
