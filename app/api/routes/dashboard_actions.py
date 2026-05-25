from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel


class DashboardManualBacktestRequest(BaseModel):
    ticker: str
    strategy_id: str
    timeframe: str
    start: datetime
    end: datetime
    slippage_pct: float | None = None
    k: float = 0.5


class UniverseRebalanceRequest(BaseModel):
    tickers: list[str] | None = None


def create_dashboard_actions_router(
    *,
    require_dashboard_session: Callable[..., dict[str, object]],
    start_manual_backtest: Callable[..., Awaitable[dict[str, object]]],
    rebalance_universe: Callable[..., dict[str, object]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/dashboard/backtests/manual-run")
    async def dashboard_backtests_manual_run(
        req: DashboardManualBacktestRequest,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        return await start_manual_backtest(
            ticker=req.ticker,
            strategy_id=req.strategy_id,
            timeframe=req.timeframe,
            start=req.start,
            end=req.end,
            slippage_pct=req.slippage_pct,
            k=req.k,
        )

    @router.post("/dashboard/universe/rebalance")
    def dashboard_universe_rebalance(
        req: UniverseRebalanceRequest,
        _: dict[str, object] = Depends(require_dashboard_session),
    ) -> dict[str, object]:
        return rebalance_universe(tickers=req.tickers, changed_by="webui")

    return router
