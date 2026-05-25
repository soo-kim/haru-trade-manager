import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request as FastAPIRequest
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.bootstrap import build_core_services
from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings
from app.db.base import Base
import app.db.models  # noqa: F401
from app.db.models.candle import Candle as CandleRow
from app.db.models.universe import Symbol
from app.db.session import SessionLocal, engine
from app.domain.models import Candle, Signal
from app.domain.universe_status import UniverseStatus, universe_status_label_ko
from app.integrations.kiwoom import KiwoomApiClient, KiwoomMarketDataGateway
from app.services.backtest_scheduler import AutoBacktestScheduler
from app.services.daily_report import DailyIncidentReporter
from app.services.live_preflight import LivePreflightService
from app.services.runtime_factory import run_live_connectivity_check
from app.services.telegram_command_service import TelegramCommandService
from app.api.routes import (
    create_dashboard_actions_router,
    create_auth_router,
    create_dashboard_analytics_router,
    create_dashboard_read_router,
    create_dashboard_records_router,
    create_system_core_router,
)
from app.services.universe_bootstrap import bootstrap_candles_on_first_run as ub_bootstrap_candles_on_first_run
from app.services.universe_bootstrap import bootstrap_universe_on_first_run as ub_bootstrap_universe_on_first_run
from app.services.universe_bootstrap import candle_bootstrap_coverage as ub_candle_bootstrap_coverage
from app.services.universe_bootstrap import fetch_prd_initial_universe_seed as ub_fetch_prd_initial_universe_seed
from app.services.universe_bootstrap import migrate_universe_source_labels as ub_migrate_universe_source_labels
from app.services.universe_bootstrap import normalize_universe_source as ub_normalize_universe_source
from app.services.universe_bootstrap import (
    recompute_active_universe_from_daily_liquidity as ub_recompute_active_universe_from_daily_liquidity,
)
from app.strategies.impl.ema_pullback import EmaPullbackStrategy
from app.strategies.impl.gap_momentum import GapMomentumStrategy
from app.strategies.impl.support_resistance import SupportResistanceStrategy
from app.strategies.impl.volatility_breakout import VolatilityBreakoutStrategy
from app.strategies.impl.volume_surge import VolumeSurgeStrategy

logger = logging.getLogger("uvicorn.error")
_DASHBOARD_TEMPLATE_DIR = Path(__file__).resolve().parent / "web" / "templates"
_SERVER_TZ = ZoneInfo(settings.server_timezone)


def _handle_config_changed(key: str, value: str, changed_by: str) -> None:
    if key != "liquidity_threshold":
        return
    try:
        with SessionLocal() as db:
            liquidity = _recompute_active_universe_from_daily_liquidity(db)
            db.commit()
        startup_bootstrap_status["active_recompute"] = liquidity
        logger.info(
            "liquidity_threshold_recomputed changed_by=%s value=%s active_count=%s",
            changed_by,
            value,
            int(liquidity.get("active_count", 0)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("liquidity_threshold_recompute_failed changed_by=%s value=%s error=%s", changed_by, value, exc)


_core_services = build_core_services(on_config_change=_handle_config_changed)
config_manager = _core_services.config_manager
alert_sink = _core_services.alert_sink
config_service = _core_services.config_service
runtime_state = _core_services.runtime_state
safety_manager = _core_services.safety_manager
runtime_bundle = _core_services.runtime_bundle
loop_runtime = _core_services.loop_runtime
loop_background = _core_services.loop_background
performance_service = _core_services.performance_service
backtest_service = _core_services.backtest_service
auth_audit_service = _core_services.auth_audit_service
auth_service = _core_services.auth_service
universe_repo = _core_services.universe_repo
candle_repo = _core_services.candle_repo
ordering_repo = _core_services.ordering_repo
config_repo = _core_services.config_repo
paper_repo = _core_services.paper_repo
strategy_performance_service = _core_services.strategy_performance_service
paper_report_service = _core_services.paper_report_service
daily_reporter = DailyIncidentReporter(
    safety=safety_manager,
    alert_sink=alert_sink,
    backtest_status_provider=lambda: auto_backtest_scheduler.status(),
    strategy_summary_provider=lambda: strategy_performance_service.report(
        limit=8,
        sort_by="total_pnl",
        sort_order="desc",
        min_trades=1,
    ),
)
telegram_service = TelegramCommandService(
    config=config_service,
    runtime=runtime_state,
    report_provider=lambda: daily_reporter.build_report_text(datetime.now().date()),
    paper_report_provider=paper_report_service.build_report,
    backtest_status_provider=lambda: auto_backtest_scheduler.status(),
    runtime_status_provider=lambda: {
        "loop_running": loop_background.status().running,
        "loop_cycles": loop_background.status().cycles,
        "loop_last_ms": loop_background.status().last_duration_ms,
    },
)
live_preflight = LivePreflightService(
    runtime=runtime_state,
    loop_runtime=loop_runtime,
    background_status=lambda: {"running": loop_background.status().running},
    connectivity_checker=lambda ticker: run_live_connectivity_check(ticker=ticker),
)
auto_backtest_scheduler = AutoBacktestScheduler(
    backtest_service=backtest_service,
    candles_provider=lambda: _load_auto_backtest_candles(),
    slippage_pct_provider=lambda: _backtest_slippage_default(),
    now_fn=lambda: datetime.now(_SERVER_TZ),
    enabled=settings.enable_auto_backtest,
    run_hour=settings.auto_backtest_run_hour,
)
runtime_bundle.maintenance_service.after_aggregate = auto_backtest_scheduler.trigger_if_due_background
startup_bootstrap_status: dict[str, object] = {
    "attempted": False,
    "bootstrapped": False,
    "source": None,
    "message": "not_started",
}
startup_bootstrap_task: asyncio.Task[None] | None = None


class PerformanceSnapshotRequest(BaseModel):
    snapshot_time: datetime
    snapshot_type: str
    total_assets: float
    cash: float
    stock_value: float
    margin_used: float = 0.0
    open_positions: int = 0


class CashFlowRequest(BaseModel):
    flow_time: datetime
    amount: float
    total_before: float
    total_after: float
    detected_by: str = "manual"


class BacktestCandleRequest(BaseModel):
    open: float
    high: float
    low: float
    close: float
    ts: datetime
    volume: float = 0.0


class BacktestSignalRequest(BaseModel):
    index: int
    side: str
    ticker: str
    strategy_id: str = "default"
    timeframe: str = "5m"
    price: float | None = None
    signal_time: datetime | None = None


class BacktestRunRequest(BaseModel):
    candles: list[BacktestCandleRequest]
    signals: list[BacktestSignalRequest]
    slippage_pct: float | None = None


class UniverseUpsertRequest(BaseModel):
    ticker: str
    name: str
    market: str
    in_universe: bool = True
    is_active: bool = False
    is_blocked: bool = False
    status: UniverseStatus = UniverseStatus.NORMAL


def _ensure_schema() -> None:
    # 신규 환경에서 마이그레이션 누락으로 핵심 테이블이 없어도 서비스가 즉시 기동되도록 보장한다.
    Base.metadata.create_all(bind=engine)


_SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("3m", "5m", "15m", "60m", "1d")


def _normalize_universe_source(value: str | None) -> str | None:
    return ub_normalize_universe_source(value)


def _fetch_prd_initial_universe_seed() -> dict[str, object]:
    return ub_fetch_prd_initial_universe_seed()


def _migrate_universe_source_labels() -> dict[str, object]:
    return ub_migrate_universe_source_labels(
        session_factory=SessionLocal,
        universe_repo=universe_repo,
        normalize_source=_normalize_universe_source,
        logger=logger,
    )


_INITIAL_BOOTSTRAP_TIMEFRAMES: tuple[str, ...] = (
    "1d",
    "3m",
    "5m",
    "15m",
    "60m",
)


def _candle_bootstrap_coverage(db) -> dict[str, object]:
    return ub_candle_bootstrap_coverage(
        db,
        universe_repo=universe_repo,
        timeframes=_INITIAL_BOOTSTRAP_TIMEFRAMES,
    )


def _recompute_active_universe_from_daily_liquidity(db) -> dict[str, object]:
    return ub_recompute_active_universe_from_daily_liquidity(
        db,
        config_manager=config_manager,
        universe_repo=universe_repo,
        candle_repo=candle_repo,
    )


async def _bootstrap_candles_on_first_run(*, tickers: list[str]) -> dict[str, object]:
    return await ub_bootstrap_candles_on_first_run(
        tickers=tickers,
        timeframes=_INITIAL_BOOTSTRAP_TIMEFRAMES,
        session_factory=SessionLocal,
        candle_repo=candle_repo,
        kiwoom_app_key=settings.kiwoom_app_key,
        kiwoom_app_secret=settings.kiwoom_app_secret,
        rate_limited_client_factory=RateLimitedClient,
        kiwoom_api_client_factory=KiwoomApiClient,
        kiwoom_market_data_gateway_factory=KiwoomMarketDataGateway,
    )


async def _run_post_seed_bootstrap(*, tickers: list[str]) -> None:
    global startup_bootstrap_status
    candles_status = await _bootstrap_candles_on_first_run(tickers=tickers)
    startup_bootstrap_status["candle_bootstrap"] = candles_status
    with SessionLocal() as db:
        liquidity = _recompute_active_universe_from_daily_liquidity(db)
        db.commit()
    startup_bootstrap_status["active_recompute"] = liquidity
    if candles_status.get("ok"):
        startup_bootstrap_status["message"] = (
            f"{startup_bootstrap_status.get('message', '-')};candles={candles_status.get('candles_inserted', 0)}"
        )
    else:
        startup_bootstrap_status["message"] = (
            f"{startup_bootstrap_status.get('message', '-')};candles_failed:{candles_status.get('message', '-')}"
        )


def _bootstrap_universe_on_first_run() -> dict[str, object]:
    return ub_bootstrap_universe_on_first_run(
        session_factory=SessionLocal,
        universe_repo=universe_repo,
        seed_fetcher=_fetch_prd_initial_universe_seed,
        normalize_source=_normalize_universe_source,
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _ensure_schema()
    config_service.load_from_db()
    global startup_bootstrap_status, startup_bootstrap_task
    source_migration = _migrate_universe_source_labels()
    startup_bootstrap_status = _bootstrap_universe_on_first_run()
    startup_bootstrap_status["source_label_migration"] = source_migration
    if startup_bootstrap_status.get("bootstrapped"):
        with SessionLocal() as db:
            rows = universe_repo.list_symbols(db, in_universe=True, limit=20_000)
            bootstrap_tickers = [x.ticker for x in rows]
        startup_bootstrap_status["message"] = f"{startup_bootstrap_status.get('message', '-')};candles_bootstrap_running"
        startup_bootstrap_status["candle_bootstrap"] = {
            "attempted": True,
            "ok": False,
            "message": "running",
            "ticker_count": len(bootstrap_tickers),
        }
        startup_bootstrap_task = asyncio.create_task(_run_post_seed_bootstrap(tickers=bootstrap_tickers))
    else:
        with SessionLocal() as db:
            coverage = _candle_bootstrap_coverage(db)
            liquidity = _recompute_active_universe_from_daily_liquidity(db)
            rows = universe_repo.list_symbols(db, in_universe=True, limit=20_000)
            bootstrap_tickers = [x.ticker for x in rows]
            db.commit()
        startup_bootstrap_status["candle_coverage"] = coverage
        startup_bootstrap_status["active_recompute"] = liquidity
        startup_bootstrap_status["message"] = (
            f"{startup_bootstrap_status.get('message', '-')};candles_bootstrap_running_existing"
        )
        startup_bootstrap_status["candle_bootstrap"] = {
            "attempted": True,
            "ok": False,
            "message": "running",
            "ticker_count": len(bootstrap_tickers),
        }
        startup_bootstrap_task = asyncio.create_task(_run_post_seed_bootstrap(tickers=bootstrap_tickers))
    if settings.enable_background_loops:
        await loop_background.start()
    yield
    if startup_bootstrap_task is not None and not startup_bootstrap_task.done():
        startup_bootstrap_task.cancel()
        try:
            await startup_bootstrap_task
        except asyncio.CancelledError:
            pass
    await loop_background.stop()


app = FastAPI(title="haru-trade-manager (rebuild)", lifespan=lifespan)
SESSION_COOKIE_NAME = "haru_session"


def _client_ip(request: FastAPIRequest) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate
    if request.client is not None and request.client.host:
        return request.client.host
    return "알수없음"


def _require_dashboard_session(request: FastAPIRequest) -> dict[str, object]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id is None:
        raise HTTPException(status_code=401, detail="session_missing")
    result = auth_service.validate_session(session_id=session_id, ip=_client_ip(request))
    if not result.get("ok"):
        raise HTTPException(status_code=401, detail=str(result.get("error", "unauthorized")))
    return result


def _runtime_snapshot() -> dict[str, object]:
    pending = runtime_state.pending_change
    bg = loop_background.status()
    return {
        "entry_paused": runtime_state.entry_paused,
        "all_paused": runtime_state.all_paused,
        "halted": runtime_state.halted,
        "halt_reason": runtime_state.halt_reason,
        "halted_at": runtime_state.halted_at.isoformat() if runtime_state.halted_at is not None else None,
        "critical_events": [
            {"level": e.level, "code": e.code, "message": e.message, "created_at": e.created_at.isoformat()}
            for e in safety_manager.latest_events(limit=20)
        ],
        "loop_runtime": loop_runtime.health_snapshot(),
        "loop_background": {
            "running": bg.running,
            "interval_seconds": bg.interval_seconds,
            "last_started_at": bg.last_started_at.isoformat() if bg.last_started_at is not None else None,
            "last_completed_at": bg.last_completed_at.isoformat() if bg.last_completed_at is not None else None,
            "last_duration_ms": bg.last_duration_ms,
            "last_error": bg.last_error,
            "cycles": bg.cycles,
        },
        "pending_change": None if pending is None else {"key": pending.key, "value": pending.value},
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/system/performance/snapshot")
def add_performance_snapshot(req: PerformanceSnapshotRequest) -> dict[str, object]:
    return performance_service.record_snapshot(
        snapshot_time=req.snapshot_time,
        snapshot_type=req.snapshot_type,
        total_assets=req.total_assets,
        cash=req.cash,
        stock_value=req.stock_value,
        margin_used=req.margin_used,
        open_positions=req.open_positions,
    )


@app.post("/system/performance/cash-flow")
def add_cash_flow(req: CashFlowRequest) -> dict[str, object]:
    return performance_service.record_cash_flow(
        flow_time=req.flow_time,
        amount=req.amount,
        total_before=req.total_before,
        total_after=req.total_after,
        detected_by=req.detected_by,
    )


@app.post("/system/performance/cash-flow/detect")
def detect_cash_flows(
    start: str | None = None,
    end: str | None = None,
    min_amount: float | None = None,
) -> dict[str, object]:
    return performance_service.detect_cash_flows(
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        min_amount=min_amount,
    )


@app.get("/system/performance/snapshots")
def list_performance_snapshots(
    start: str | None = None,
    end: str | None = None,
    snapshot_type: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, object]:
    return performance_service.list_snapshot_records(
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        snapshot_type=snapshot_type,
        offset=max(offset, 0),
        limit=max(1, min(limit, 1000)),
    )


@app.get("/system/performance/cash-flows")
def list_performance_cash_flows(
    start: str | None = None,
    end: str | None = None,
    detected_by: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, object]:
    return performance_service.list_cash_flow_records(
        start=_parse_datetime(start),
        end=_parse_datetime(end),
        detected_by=detected_by,
        offset=max(offset, 0),
        limit=max(1, min(limit, 1000)),
    )


@app.get("/system/performance/twr")
def get_twr_report(start: str | None = None, end: str | None = None) -> dict[str, object]:
    return performance_service.twr_report(start=_parse_datetime(start), end=_parse_datetime(end))


@app.get("/paper_report")
def paper_report() -> dict[str, object]:
    return paper_report_service.build_report()


@app.post("/system/backtest/run")
async def run_backtest(req: BacktestRunRequest) -> dict[str, object]:
    slippage_pct = _backtest_slippage_default() if req.slippage_pct is None else req.slippage_pct
    if slippage_pct < 0 or slippage_pct > 0.5:
        return {"ok": False, "error": "slippage_pct must be between 0 and 0.5"}

    candles = [
        Candle(open=x.open, high=x.high, low=x.low, close=x.close, ts=x.ts, volume=x.volume)
        for x in req.candles
    ]
    signals = [
        Signal(
            index=x.index,
            side=x.side,
            ticker=x.ticker,
            strategy_id=x.strategy_id,
            timeframe=x.timeframe,
            price=x.price,
            signal_time=x.signal_time,
        )
        for x in req.signals
    ]
    first_signal = signals[0] if signals else None
    job_id = await backtest_service.start_job(
        candles=candles,
        signals=signals,
        slippage_pct=slippage_pct,
        meta={
            "source": "system_api",
            "ticker": first_signal.ticker if first_signal is not None else None,
            "strategy_id": first_signal.strategy_id if first_signal is not None else None,
            "timeframe": first_signal.timeframe if first_signal is not None else None,
            "candles": len(candles),
            "signals": len(signals),
            **_backtest_risk_meta(),
        },
    )
    return {"ok": True, "job_id": job_id, "status": "queued"}


@app.get("/system/backtest/jobs")
async def list_backtest_jobs(
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> dict[str, object]:
    total = await backtest_service.count_jobs(status=status)
    jobs = await backtest_service.list_jobs(
        limit=max(1, min(limit, 200)),
        offset=max(offset, 0),
        status=status,
    )
    return {
        "ok": True,
        "meta": {"total": total, "offset": max(offset, 0), "limit": max(1, min(limit, 200)), "status": status},
        "items": jobs,
    }


@app.get("/system/backtest/jobs/{job_id}")
async def get_backtest_job(job_id: str) -> dict[str, object]:
    job = await backtest_service.get_job(job_id)
    if job is None:
        return {"ok": False, "error": "job_not_found", "job_id": job_id}
    return {"ok": True, **job}


@app.get("/system/backtest/auto/status")
def auto_backtest_status() -> dict[str, object]:
    return {"ok": True, "status": auto_backtest_scheduler.status()}


@app.post("/system/backtest/auto/run-now")
async def auto_backtest_run_now() -> dict[str, object]:
    return await auto_backtest_scheduler.trigger_now(reason="manual_api")


@app.get("/system/universe")
def list_universe(
    runtime_only: bool = False,
    in_universe: bool | None = None,
    market: str | None = None,
    is_active: bool | None = None,
    is_blocked: bool | None = None,
    status: str | None = None,
    q: str | None = None,
    offset: int = 0,
    limit: int = 500,
) -> dict[str, object]:
    try:
        with SessionLocal() as db:
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
                offset=max(offset, 0),
                limit=max(1, min(limit, 2000)),
            )
        return {
            "ok": True,
            "meta": {"total": total, "offset": max(offset, 0), "limit": max(1, min(limit, 2000))},
            "items": [_symbol_to_dict(x) for x in rows],
        }
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc), "items": []}


@app.post("/system/universe/upsert")
def upsert_universe_symbol(req: UniverseUpsertRequest) -> dict[str, object]:
    try:
        market = _normalize_universe_source(req.market)
        if market is None:
            return {"ok": False, "error": "market_must_be_KOSPI200_or_KOSDAQ150_or_USER"}
        with SessionLocal() as db:
            row = universe_repo.upsert_symbol(
                db,
                ticker=req.ticker,
                name=req.name,
                market=market,
                in_universe=req.in_universe,
                is_active=req.is_active,
                is_blocked=req.is_blocked,
                status=req.status,
            )
        return {"ok": True, "item": _symbol_to_dict(row)}
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/system/universe/{ticker}/block")
def block_universe_symbol(ticker: str, blocked: bool = True) -> dict[str, object]:
    try:
        with SessionLocal() as db:
            row = universe_repo.set_blocked(db, ticker=ticker, blocked=blocked)
        return {"ok": True, "item": _symbol_to_dict(row)}
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc), "ticker": ticker}
    except KeyError:
        return {"ok": False, "error": "symbol_not_found", "ticker": ticker}


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    return datetime.fromisoformat(value)


def _normalize_strategy_id(strategy_id: str) -> str:
    token = strategy_id.strip().lower()
    aliases = {
        "1": "1",
        "gap": "1",
        "gap_momentum": "1",
        "2": "2",
        "ema": "2",
        "ema_pullback": "2",
        "3": "3",
        "breakout": "3",
        "volatility_breakout": "3",
        "4": "4",
        "volume": "4",
        "volume_surge": "4",
        "5": "5",
        "support": "5",
        "support_resistance": "5",
    }
    return aliases.get(token, strategy_id.strip())


def _build_strategy_instance(*, strategy_id: str, timeframe: str, k: float) -> object:
    normalized = _normalize_strategy_id(strategy_id)
    if normalized == "1":
        return GapMomentumStrategy(timeframe=timeframe)
    if normalized == "2":
        return EmaPullbackStrategy(timeframe=timeframe)
    if normalized == "3":
        return VolatilityBreakoutStrategy(timeframe=timeframe, k=k)
    if normalized == "4":
        return VolumeSurgeStrategy(timeframe=timeframe)
    if normalized == "5":
        return SupportResistanceStrategy(timeframe=timeframe)
    raise ValueError(f"지원하지 않는 strategy_id: {strategy_id}")


def _backtest_risk_meta() -> dict[str, float]:
    return {
        "atr_period": float(config_manager.get("atr_period")),
        "stop_atr_mult": float(config_manager.get("stop_atr_mult")),
        "tp_atr_mult": float(config_manager.get("tp_atr_mult")),
        "trail_atr_mult": float(config_manager.get("trail_atr_mult")),
    }


def _backtest_slippage_default() -> float:
    value = float(config_manager.get("slippage_pct"))
    return min(max(value, 0.0), 0.5)


async def _start_manual_backtest(
    *,
    ticker: str,
    strategy_id: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    slippage_pct: float | None = None,
    k: float = 0.5,
) -> dict[str, object]:
    effective_slippage_pct = _backtest_slippage_default() if slippage_pct is None else slippage_pct
    if end <= start:
        return {"ok": False, "error": "end must be after start"}
    if effective_slippage_pct < 0 or effective_slippage_pct > 0.5:
        return {"ok": False, "error": "slippage_pct must be between 0 and 0.5"}
    clean_timeframe = timeframe.strip()
    if clean_timeframe not in _SUPPORTED_TIMEFRAMES:
        return {"ok": False, "error": f"unsupported timeframe: {clean_timeframe}"}
    clean_ticker = ticker.strip()

    try:
        strategy = _build_strategy_instance(strategy_id=strategy_id, timeframe=clean_timeframe, k=k)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        with SessionLocal() as db:
            rows = candle_repo.list_range(
                db,
                ticker=clean_ticker,
                timeframe=clean_timeframe,
                start=start,
                end=end,
                limit=100_000,
            )
    except SQLAlchemyError as exc:
        msg = str(exc)
        if "rebuild_candles" in msg:
            return {
                "ok": False,
                "error": "캔들 테이블이 없습니다. 스키마 초기화 또는 마이그레이션이 필요합니다.",
            }
        return {"ok": False, "error": msg}

    if len(rows) < 2:
        return {
            "ok": False,
            "error": "백테스트 대상 캔들이 없습니다. 유니버스/캔들 수집을 먼저 실행해 주세요.",
        }

    candles = [
        Candle(
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            ts=row.candle_time,
            volume=row.volume,
        )
        for row in rows
    ]
    signals: list[Signal] = []
    for idx in range(len(candles) - 1):
        window = candles[: idx + 1]
        now = window[-1].ts
        signal = strategy.generate(ticker=clean_ticker, candles=window, now=now)
        if signal is None:
            continue
        signals.append(
            Signal(
                index=idx,
                side=signal.side,
                ticker=clean_ticker,
                strategy_id=signal.strategy_id,
                timeframe=clean_timeframe,
                price=signal.price,
                signal_time=signal.signal_time,
            )
        )

    job_id = await backtest_service.start_job(
        candles=candles,
        signals=signals,
        slippage_pct=effective_slippage_pct,
        meta={
            "source": "dashboard_manual",
            "ticker": clean_ticker,
            "strategy_id": _normalize_strategy_id(strategy_id),
            "timeframe": clean_timeframe,
            "candles": len(candles),
            "signals": len(signals),
            "start": start.isoformat(),
            "end": end.isoformat(),
            **_backtest_risk_meta(),
        },
    )
    return {
        "ok": True,
        "job_id": job_id,
        "status": "queued",
        "meta": {
            "ticker": clean_ticker,
            "strategy_id": _normalize_strategy_id(strategy_id),
            "timeframe": clean_timeframe,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "candles": len(candles),
            "signals": len(signals),
            "slippage_pct": effective_slippage_pct,
            "k": k,
        },
    }


def _rebalance_universe(*, tickers: list[str] | None, changed_by: str) -> dict[str, object]:
    try:
        with SessionLocal() as db:
            current_rows = universe_repo.list_symbols(db, limit=20_000)
            current = {x.ticker: x for x in current_rows}
            open_positions = {x.ticker for x in ordering_repo.list_open_positions(db)}

            manual_source = [x.strip() for x in (tickers or []) if x and x.strip()]
            source_type = "manual"
            source_items: list[dict[str, str]] = []
            logger.info(
                "universe_rebalance_start changed_by=%s source=%s requested_count=%s",
                changed_by,
                source_type if manual_source else "prd_index_constituents",
                len(set(manual_source)),
            )
            if manual_source:
                for ticker in sorted(set(manual_source)):
                    row = current.get(ticker)
                    source_items.append(
                        {
                            "ticker": ticker,
                            "market": "USER" if row is None else (_normalize_universe_source(row.market) or "USER"),
                            "name": row.name if row is not None else ticker,
                        }
                    )
            else:
                source_type = "prd_index_constituents"
                seeds = _fetch_prd_initial_universe_seed()
                if not seeds.get("ok"):
                    return {
                        "ok": False,
                        "error": f"초기 유니버스(코스피200+코스닥150) 조회 실패: {seeds.get('error', 'unknown')}",
                    }
                raw_items = seeds.get("items", [])
                if not isinstance(raw_items, list) or not raw_items:
                    return {
                        "ok": False,
                        "error": "초기 유니버스(코스피200+코스닥150) 조회 결과가 비어 있습니다.",
                    }
                by_ticker: dict[str, dict[str, str]] = {}
                for item in raw_items:
                    ticker = str(item.get("ticker", "")).strip()
                    if not ticker:
                        continue
                    source_label = _normalize_universe_source(str(item.get("market", "")))
                    if source_label is None:
                        return {
                            "ok": False,
                            "error": f"초기 유니버스 소스 라벨 오류: {item.get('market')}",
                        }
                    by_ticker[ticker] = {
                        "ticker": ticker,
                        "market": source_label,
                        "name": str(item.get("name", ticker)).strip() or ticker,
                    }
                source_items = [by_ticker[ticker] for ticker in sorted(by_ticker.keys())]

            target = [item["ticker"] for item in source_items]
            if not target:
                return {"ok": False, "error": "리밸런싱 대상 종목이 없습니다."}
            source_map = {item["ticker"]: item for item in source_items}

            added: list[str] = []
            removed: list[str] = []
            pending_exit: list[str] = []
            kept: list[str] = []

            target_set = set(target)
            for ticker in target:
                row = current.get(ticker)
                src = source_map.get(ticker, {})
                if row is None:
                    db.add(
                        Symbol(
                            ticker=ticker,
                            name=str(src.get("name", ticker)),
                            market=str(src.get("market", "USER")),
                            in_universe=True,
                            is_active=False,
                            is_blocked=False,
                            status=UniverseStatus.NORMAL.value,
                        )
                    )
                    added.append(ticker)
                    continue
                row.name = str(src.get("name", row.name))
                row.market = str(src.get("market", row.market))
                row.in_universe = True
                if row.status in {UniverseStatus.REMOVED.value, UniverseStatus.EXIT_PENDING.value} and ticker not in open_positions:
                    row.status = UniverseStatus.NORMAL.value
                kept.append(ticker)

            for ticker, row in current.items():
                if not row.in_universe or ticker in target_set:
                    continue
                if ticker in open_positions:
                    row.status = UniverseStatus.EXIT_PENDING.value
                    row.is_active = False
                    pending_exit.append(ticker)
                else:
                    row.in_universe = False
                    row.is_active = False
                    row.status = UniverseStatus.REMOVED.value
                    removed.append(ticker)

            liquidity_summary = _recompute_active_universe_from_daily_liquidity(db)
            db.commit()
            logger.info(
                "universe_rebalance_done changed_by=%s source=%s target=%s added=%s removed=%s pending_exit=%s active=%s",
                changed_by,
                source_type,
                len(target),
                len(added),
                len(removed),
                len(pending_exit),
                int(liquidity_summary.get("active_count", 0)),
            )

            return {
                "ok": True,
                "summary": {
                    "source": source_type,
                    "target_count": len(target),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "pending_exit_count": len(pending_exit),
                    "kept_count": len(kept),
                    "active_count": int(liquidity_summary.get("active_count", 0)),
                    "liquidity_threshold_eok": float(liquidity_summary.get("threshold_eok", 0.0)),
                },
                "data": {
                    "added": added,
                    "removed": removed,
                    "pending_exit": pending_exit,
                },
            }
    except SQLAlchemyError as exc:
        logger.exception("universe_rebalance_db_error changed_by=%s error=%s", changed_by, exc)
        return {"ok": False, "error": str(exc)}


def _load_auto_backtest_candles(limit: int = 240, timeframe: str = "5m") -> list[Candle]:
    try:
        tickers = loop_runtime.tickers_provider()
        if not tickers:
            return []
        target = tickers[0]
        with SessionLocal() as db:
            rows = candle_repo.list_recent(db, ticker=target, timeframe=timeframe, limit=limit)
        return [
            Candle(
                open=x.open,
                high=x.high,
                low=x.low,
                close=x.close,
                ts=x.candle_time,
                volume=x.volume,
            )
            for x in rows
        ]
    except Exception:  # noqa: BLE001
        return []


def _symbol_to_dict(row: object) -> dict[str, object]:
    status = str(getattr(row, "status"))
    return {
        "ticker": getattr(row, "ticker"),
        "name": getattr(row, "name"),
        "market": getattr(row, "market"),
        "in_universe": getattr(row, "in_universe"),
        "is_active": getattr(row, "is_active"),
        "is_blocked": getattr(row, "is_blocked"),
        "status": status,
        "status_label_ko": universe_status_label_ko(status),
    }


def _dashboard_setting_item(*, key: str, value: str, webui_only_keys: set[str]) -> dict[str, object]:
    meta = config_service.describe(key)
    item: dict[str, object] = {
        "key": key,
        "value": value,
        "editable": key != "daily_base_capital",
        "webui_only": key in webui_only_keys or key.startswith("strategy."),
        "label": meta.get("label", key),
        "description": meta.get("description", ""),
    }
    allowed_values = meta.get("allowed_values")
    if isinstance(allowed_values, list) and allowed_values:
        item["allowed_values"] = [str(x) for x in allowed_values]
    return item


def _position_to_dict(row: object, *, current_price: float | None = None) -> dict[str, object]:
    entry_price = float(getattr(row, "entry_price"))
    remaining_quantity = float(getattr(row, "remaining_quantity"))
    unrealized_pnl = None
    unrealized_pnl_pct = None
    if current_price is not None and remaining_quantity > 0:
        unrealized_pnl = (float(current_price) - entry_price) * remaining_quantity
        if entry_price > 0:
            unrealized_pnl_pct = ((float(current_price) / entry_price) - 1.0) * 100.0
    return {
        "id": getattr(row, "id"),
        "ticker": getattr(row, "ticker"),
        "strategy_id": getattr(row, "strategy_id"),
        "state": getattr(row, "state"),
        "entry_price": entry_price,
        "stop_price": getattr(row, "stop_price"),
        "take_profit_price": getattr(row, "take_profit_price"),
        "trailing_stop_price": getattr(row, "trailing_stop_price"),
        "highest_price": getattr(row, "highest_price"),
        "quantity": getattr(row, "quantity"),
        "remaining_quantity": remaining_quantity,
        "current_price": current_price,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "entry_time": getattr(row, "entry_time").isoformat() if getattr(row, "entry_time") is not None else None,
        "closed_time": getattr(row, "closed_time").isoformat() if getattr(row, "closed_time") is not None else None,
        "close_reason": getattr(row, "close_reason"),
    }


def _config_history_to_dict(row: object) -> dict[str, object]:
    return {
        "id": getattr(row, "id"),
        "key": getattr(row, "key"),
        "old_value": getattr(row, "old_value"),
        "new_value": getattr(row, "new_value"),
        "changed_by": getattr(row, "changed_by"),
        "changed_at": getattr(row, "changed_at").isoformat() if getattr(row, "changed_at") is not None else None,
    }


def _find_nearest_closed_position(*, trade: object, candidates: list[object]) -> object | None:
    created_at = getattr(trade, "created_at")
    if created_at is None or not candidates:
        return None
    nearest = None
    nearest_gap = None
    for pos in candidates:
        closed_at = getattr(pos, "closed_time")
        if closed_at is None:
            continue
        gap = abs((closed_at - created_at).total_seconds())
        if nearest_gap is None or gap < nearest_gap:
            nearest = pos
            nearest_gap = gap
    if nearest_gap is None:
        return None
    # 서로 다른 거래를 과도하게 잘못 매칭하지 않도록 48시간 이내만 허용한다.
    return nearest if nearest_gap <= 172_800 else None


def _trade_to_dict(row: object, *, closed_position: object | None = None) -> dict[str, object]:
    entry_price = float(getattr(row, "entry_price"))
    exit_price_raw = getattr(row, "exit_price")
    exit_price = float(exit_price_raw) if exit_price_raw is not None else None
    pnl_raw = getattr(row, "pnl")
    pnl = float(pnl_raw) if pnl_raw is not None else None
    pnl_pct = None
    if pnl is not None and entry_price > 0:
        pnl_pct = (pnl / entry_price) * 100.0
    trade_time = getattr(row, "created_at")
    entry_time = trade_time
    exit_time = trade_time
    holding_minutes = None
    close_reason = None
    if closed_position is not None:
        entry_time = getattr(closed_position, "entry_time") or entry_time
        exit_time = getattr(closed_position, "closed_time") or exit_time
        close_reason = getattr(closed_position, "close_reason")
        if entry_time is not None and exit_time is not None:
            holding_minutes = max(int((exit_time - entry_time).total_seconds() // 60), 0)
    return {
        "id": getattr(row, "id"),
        "ticker": getattr(row, "ticker"),
        "strategy_id": getattr(row, "strategy_id"),
        "side": getattr(row, "side"),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "quantity": float(getattr(row, "quantity")),
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "entry_time": entry_time.isoformat() if entry_time is not None else None,
        "exit_time": exit_time.isoformat() if exit_time is not None else None,
        "holding_minutes": holding_minutes,
        "close_reason": close_reason,
    }


def _load_dashboard_html(filename: str) -> str:
    path = _DASHBOARD_TEMPLATE_DIR / filename
    return path.read_text(encoding="utf-8")


app.include_router(
    create_system_core_router(
        config_service=config_service,
        runtime_snapshot_provider=_runtime_snapshot,
        loop_background=loop_background,
        loop_runtime=loop_runtime,
        telegram_service=telegram_service,
        daily_reporter=daily_reporter,
        live_preflight=live_preflight,
        live_connectivity_checker=run_live_connectivity_check,
    )
)

app.include_router(
    create_dashboard_read_router(
        require_dashboard_session=_require_dashboard_session,
        runtime_snapshot_provider=_runtime_snapshot,
        performance_service=performance_service,
        paper_report_service=paper_report_service,
        live_connectivity_checker=run_live_connectivity_check,
        startup_bootstrap_status=startup_bootstrap_status,
        backtest_service=backtest_service,
        session_factory=SessionLocal,
        universe_repo=universe_repo,
        symbol_to_dict=_symbol_to_dict,
        candle_row_model=CandleRow,
        supported_timeframes=_SUPPORTED_TIMEFRAMES,
    )
)

app.include_router(
    create_dashboard_actions_router(
        require_dashboard_session=_require_dashboard_session,
        start_manual_backtest=_start_manual_backtest,
        rebalance_universe=_rebalance_universe,
    )
)

app.include_router(
    create_dashboard_analytics_router(
        require_dashboard_session=_require_dashboard_session,
        parse_datetime=_parse_datetime,
        performance_service=performance_service,
        strategy_performance_service=strategy_performance_service,
        session_factory=SessionLocal,
        ordering_repo=ordering_repo,
        candle_repo=candle_repo,
        position_to_dict=_position_to_dict,
        auth_audit_service=auth_audit_service,
    )
)

app.include_router(
    create_dashboard_records_router(
        require_dashboard_session=_require_dashboard_session,
        config_service=config_service,
        dashboard_setting_item=_dashboard_setting_item,
        session_factory=SessionLocal,
        config_repo=config_repo,
        config_history_to_dict=_config_history_to_dict,
        paper_repo=paper_repo,
        ordering_repo=ordering_repo,
        parse_datetime=_parse_datetime,
        find_nearest_closed_position=_find_nearest_closed_position,
        trade_to_dict=_trade_to_dict,
    )
)

app.include_router(
    create_auth_router(
        auth_service=auth_service,
        load_dashboard_html=_load_dashboard_html,
        session_cookie_name=SESSION_COOKIE_NAME,
    )
)
