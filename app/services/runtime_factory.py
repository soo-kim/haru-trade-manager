from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import ConfigManager
from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings
from app.core.time_sync import TimeSyncService
from app.db.session import SessionLocal
from app.domain.models import Candle
from app.integrations.kiwoom import KiwoomApiClient, KiwoomMarketDataGateway, KiwoomOrderGateway
from app.loops.core import InMemorySignalQueue, LoopBScanner, LoopCMaintainer
from app.loops.loop_a_runtime import AtrProvider, LoopARunner, PriceProvider
from app.loops.loop_b_runtime import CandleFetcher, LoopBRunner
from app.orders import PaperOrderGateway, PositionStateMachine
from app.orders.service import OrderService
from app.repositories.candle import CandleRepository
from app.repositories.ordering import OrderingRepository
from app.repositories.universe import UniverseRepository
from app.risk.engine import RiskEngine
from app.services.candle_collection import CandleCollectionService
from app.services.loop_runtime import LoopRuntimeCoordinator
from app.services.runtime_safety import RuntimeSafetyManager
from app.services.trading_service import TradingService
from app.strategies.registry import StrategyRegistry

logger = logging.getLogger("uvicorn.error")


class RuntimeMaintenanceService:
    def __init__(
        self,
        *,
        now_fn: Callable[[], datetime] | None = None,
        server_timezone: str | None = None,
    ) -> None:
        self._server_tz = ZoneInfo(server_timezone or settings.server_timezone)
        self.now_fn = now_fn or (lambda: datetime.now(self._server_tz))

        self.last_refresh_at: datetime | None = None
        self.last_optimize_at: datetime | None = None
        self.last_aggregate_at: datetime | None = None
        self.after_aggregate: Callable[[], None] | None = None

        self.last_trading_ticker_count: int = 0
        self.last_tracking_ticker_count: int = 0
        self.last_universe_ticker_count: int = 0

        self.post_market_backfill_runner: Callable[[], Awaitable[dict[str, object]]] | None = None
        self.last_post_market_backfill: dict[str, object] | None = None
        self._last_post_market_slot: str | None = None
        self._post_market_task: asyncio.Task[None] | None = None

    def refresh_universe(self) -> None:
        self.last_refresh_at = self.now_fn()

    def optimize_parameters(self) -> None:
        self.last_optimize_at = self.now_fn()

    def aggregate_daily_performance(self) -> None:
        self.last_aggregate_at = self.now_fn()
        if self.after_aggregate is not None:
            try:
                self.after_aggregate()
            except Exception:  # noqa: BLE001
                pass

    def set_ticker_counts(self, *, trading: int, tracking: int, universe: int) -> None:
        self.last_trading_ticker_count = max(trading, 0)
        self.last_tracking_ticker_count = max(tracking, 0)
        self.last_universe_ticker_count = max(universe, 0)

    def runtime_metrics_snapshot(self) -> dict[str, object]:
        return {
            "ticker_counts": {
                "trading": self.last_trading_ticker_count,
                "tracking": self.last_tracking_ticker_count,
                "universe": self.last_universe_ticker_count,
            },
            "post_market_backfill": self.last_post_market_backfill,
        }

    def schedule_post_market_backfill_if_due(self) -> None:
        now_local = self.now_fn().astimezone(self._server_tz)
        if not self._is_post_market_window(now_local):
            return

        slot = now_local.strftime("%Y-%m-%d")
        if self._last_post_market_slot == slot:
            return

        if self._post_market_task is not None and not self._post_market_task.done():
            return

        self._last_post_market_slot = slot
        runner = self.post_market_backfill_runner
        if runner is None:
            self.last_post_market_backfill = {
                "ok": False,
                "slot": slot,
                "message": "runner_not_configured",
                "started_at": self.now_fn().isoformat(),
            }
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # 이벤트 루프가 없는 컨텍스트에서는 다음 loop_c 슬롯에서 재시도한다.
            self._last_post_market_slot = None
            return

        self.last_post_market_backfill = {
            "ok": False,
            "slot": slot,
            "message": "running",
            "started_at": self.now_fn().isoformat(),
        }
        self._post_market_task = loop.create_task(self._run_post_market_backfill_task(slot=slot, runner=runner))

    @staticmethod
    def _is_post_market_window(now_local: datetime) -> bool:
        total_minutes = now_local.hour * 60 + now_local.minute
        return (15 * 60 + 40) <= total_minutes <= (20 * 60)

    async def _run_post_market_backfill_task(
        self,
        *,
        slot: str,
        runner: Callable[[], Awaitable[dict[str, object]]],
    ) -> None:
        try:
            logger.info("post_market_backfill_started slot=%s", slot)
            payload = await runner()
            payload = dict(payload)
            payload.setdefault("slot", slot)
            payload.setdefault("ok", False)
            payload["completed_at"] = self.now_fn().isoformat()
            self.last_post_market_backfill = payload
            logger.info(
                "post_market_backfill_completed slot=%s ok=%s processed=%s failed=%s",
                slot,
                payload.get("ok"),
                payload.get("processed_count"),
                payload.get("failed_count"),
            )
        except Exception as exc:  # noqa: BLE001
            self.last_post_market_backfill = {
                "ok": False,
                "slot": slot,
                "message": f"backfill_failed:{exc}",
                "completed_at": self.now_fn().isoformat(),
            }
            logger.exception("post_market_backfill_failed slot=%s error=%s", slot, exc)


class DbPriceProvider(PriceProvider):
    def __init__(self, repo: CandleRepository, *, session_factory=SessionLocal) -> None:
        self.repo = repo
        self.session_factory = session_factory

    async def get_current_price(self, ticker: str) -> float:
        try:
            with self.session_factory() as db:
                value = self.repo.get_latest_close(db, ticker=ticker)
                return float(value) if value is not None else 0.0
        except SQLAlchemyError:
            return 0.0


class DbAtrProvider(AtrProvider):
    def __init__(self, repo: CandleRepository, risk_engine: RiskEngine, *, session_factory=SessionLocal) -> None:
        self.repo = repo
        self.risk_engine = risk_engine
        self.session_factory = session_factory

    async def get_atr(self, ticker: str, strategy_id: str) -> float:  # noqa: ARG002
        try:
            with self.session_factory() as db:
                rows = self.repo.list_recent(db, ticker=ticker, timeframe="5m", limit=20)
        except SQLAlchemyError:
            return 1.0

        if len(rows) < 2:
            return 1.0
        highs = [x.high for x in rows]
        lows = [x.low for x in rows]
        closes = [x.close for x in rows]
        return max(self.risk_engine.compute_atr(highs=highs, lows=lows, closes=closes), 1.0)


class DbFallbackCandleFetcher(CandleFetcher):
    def __init__(self, candle_repo: CandleRepository, *, session_factory=SessionLocal) -> None:
        self.candle_repo = candle_repo
        self.session_factory = session_factory

    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[Candle]:
        try:
            with self.session_factory() as db:
                rows = self.candle_repo.list_range(
                    db,
                    ticker=ticker,
                    timeframe=timeframe,
                    start=since,
                    end=None,
                    limit=240,
                )
        except SQLAlchemyError:
            return []

        return [
            Candle(
                open=x.open,
                high=x.high,
                low=x.low,
                close=x.close,
                volume=x.volume,
                ts=x.candle_time,
            )
            for x in rows
        ]


class LivePriceProvider(PriceProvider):
    def __init__(self, market_data: KiwoomMarketDataGateway, *, fallback: PriceProvider | None = None) -> None:
        self.market_data = market_data
        self.fallback = fallback

    async def get_current_price(self, ticker: str) -> float:
        try:
            price = await self.market_data.get_current_price(ticker)
            if price > 0:
                return price
        except Exception:  # noqa: BLE001
            pass
        if self.fallback is not None:
            return await self.fallback.get_current_price(ticker)
        return 0.0


class LiveCandleFetcher(CandleFetcher):
    def __init__(self, market_data: KiwoomMarketDataGateway) -> None:
        self.market_data = market_data

    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[Candle]:
        return await self.market_data.fetch_candles_incremental(ticker=ticker, timeframe=timeframe, since=since)


class ResilientCandleFetcher(CandleFetcher):
    def __init__(
        self,
        *,
        primary: CandleFetcher,
        fallback: CandleFetcher | None,
        retry_count: int = 1,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.retry_count = max(retry_count, 0)
        self.error_count = 0

    async def fetch_incremental(self, *, ticker: str, timeframe: str, since: datetime | None) -> list[Candle]:
        for attempt in range(self.retry_count + 1):
            try:
                return await self.primary.fetch_incremental(ticker=ticker, timeframe=timeframe, since=since)
            except Exception as exc:  # noqa: BLE001
                self.error_count += 1
                logger.warning(
                    "live_candle_fetch_failed ticker=%s timeframe=%s attempt=%s error_count=%s error=%s",
                    ticker,
                    timeframe,
                    attempt + 1,
                    self.error_count,
                    exc,
                )
                if attempt < self.retry_count:
                    await asyncio.sleep(0.15)

        if self.fallback is not None:
            return await self.fallback.fetch_incremental(ticker=ticker, timeframe=timeframe, since=since)
        return []


@dataclass
class RuntimeBundle:
    coordinator: LoopRuntimeCoordinator
    queue: InMemorySignalQueue
    maintenance_service: RuntimeMaintenanceService


def build_runtime_bundle(
    *,
    config: ConfigManager,
    safety: RuntimeSafetyManager,
    trading_mode: str | None = None,
    session_factory=SessionLocal,
    kiwoom_client: KiwoomApiClient | None = None,
) -> RuntimeBundle:
    mode = (trading_mode or settings.trading_mode).lower()
    server_tz = ZoneInfo(settings.server_timezone)
    def now_local() -> datetime:
        return datetime.now(server_tz)

    queue = InMemorySignalQueue(items=[])
    candle_repo = CandleRepository()
    universe_repo = UniverseRepository()
    ordering_repo = OrderingRepository()
    risk_engine = RiskEngine()
    maintenance_service = RuntimeMaintenanceService(now_fn=now_local, server_timezone=settings.server_timezone)
    kiwoom_live_client = kiwoom_client or KiwoomApiClient(RateLimitedClient())
    time_sync = TimeSyncService(
        provider=KiwoomOrderGateway(kiwoom_live_client),
        server_timezone=settings.server_timezone,
        now_fn=now_local,
    )

    order_gateway, price_provider, candle_fetcher = _build_gateways_and_data_sources(
        mode=mode,
        candle_repo=candle_repo,
        risk_engine=risk_engine,
        session_factory=session_factory,
        kiwoom_client=kiwoom_live_client,
    )

    order_service = OrderService(order_gateway, safety=safety)
    trading_service = TradingService(
        order_service=order_service,
        ordering_repo=ordering_repo,
        risk_engine=risk_engine,
        session_factory=session_factory,
    )

    loop_a = LoopARunner(
        queue=queue,
        signal_executor=trading_service,
        ordering_repo=ordering_repo,
        order_service=order_service,
        state_machine=PositionStateMachine(),
        price_provider=price_provider,
        atr_provider=DbAtrProvider(candle_repo, risk_engine, session_factory=session_factory),
        session_factory=session_factory,
        safety=safety,
        config=config,
    )

    scanner = LoopBScanner(strategy_engine=StrategyRegistry(), queue=queue)
    loop_b = LoopBRunner(
        scanner=scanner,
        candle_repo=candle_repo,
        candle_fetcher=candle_fetcher,
        session_factory=session_factory,
        now_fn=time_sync.aligned_now,
    )

    maintenance_service.post_market_backfill_runner = lambda: _run_post_market_daily_backfill(
        universe_repo=universe_repo,
        candle_repo=candle_repo,
        candle_fetcher=candle_fetcher,
        session_factory=session_factory,
        batch_size=20,
        batch_sleep_seconds=0.2,
    )

    loop_c = LoopCMaintainer(maintenance_service=maintenance_service)

    coordinator = LoopRuntimeCoordinator(
        loop_a=loop_a,
        loop_b=loop_b,
        loop_c=loop_c,
        tickers_provider=lambda: _load_tracking_tickers(
            universe_repo=universe_repo,
            ordering_repo=ordering_repo,
            session_factory=session_factory,
            maintenance_service=maintenance_service,
        ),
        safety=safety,
        expected_cycle_seconds=5.0,
        now_fn=time_sync.aligned_now,
        extra_metrics_provider=maintenance_service.runtime_metrics_snapshot,
        pre_loop_b_hook=time_sync.sync_if_due_pre_market,
    )
    return RuntimeBundle(coordinator=coordinator, queue=queue, maintenance_service=maintenance_service)


async def run_live_connectivity_check(
    *,
    kiwoom_client: KiwoomApiClient | None = None,
    ticker: str | None = None,
) -> dict[str, object]:
    client = kiwoom_client or KiwoomApiClient(RateLimitedClient())
    md = KiwoomMarketDataGateway(client)
    order_gateway = KiwoomOrderGateway(client)
    target_ticker = ticker or _default_check_ticker()

    result: dict[str, object] = {
        "ok": True,
        "enabled": True,
        "trading_mode": settings.trading_mode,
        "ticker": target_ticker,
        "token_ok": False,
        "server_time_ok": False,
        "price_ok": False,
    }

    try:
        token = await client.ensure_token()
        result["token_ok"] = bool(token)
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["token_error"] = str(exc)

    try:
        server_time = await order_gateway.get_server_time()
        result["server_time_ok"] = True
        result["server_time"] = server_time.isoformat()
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["server_time_error"] = str(exc)

    try:
        price = await md.get_current_price(target_ticker)
        price_ticker = target_ticker
        if price <= 0 and target_ticker != "005930":
            # 활성 유니버스가 비어있거나 테스트 티커가 비정상인 경우 오탐을 줄이기 위해 대표 종목으로 재확인한다.
            fallback_price = await md.get_current_price("005930")
            if fallback_price > 0:
                price = fallback_price
                price_ticker = "005930"
        result["price_ok"] = price > 0
        result["price"] = price
        result["price_ticker"] = price_ticker
        if price <= 0:
            result["ok"] = False
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["price_error"] = str(exc)

    return result


def _build_gateways_and_data_sources(
    *,
    mode: str,
    candle_repo: CandleRepository,
    risk_engine: RiskEngine,  # noqa: ARG001
    session_factory=SessionLocal,
    kiwoom_client: KiwoomApiClient | None = None,
) -> tuple[Any, PriceProvider, CandleFetcher]:
    db_price = DbPriceProvider(candle_repo, session_factory=session_factory)
    db_fallback = DbFallbackCandleFetcher(candle_repo, session_factory=session_factory)
    client = kiwoom_client or KiwoomApiClient(RateLimitedClient())

    if mode == "live":
        order_gateway: Any = KiwoomOrderGateway(client)
    else:
        order_gateway = PaperOrderGateway()

    market_data = KiwoomMarketDataGateway(client)
    price_provider: PriceProvider = LivePriceProvider(market_data, fallback=db_price)
    candle_fetcher: CandleFetcher = ResilientCandleFetcher(
        primary=LiveCandleFetcher(market_data),
        fallback=db_fallback,
        retry_count=1,
    )

    return order_gateway, price_provider, candle_fetcher


async def _run_post_market_daily_backfill(
    *,
    universe_repo: UniverseRepository,
    candle_repo: CandleRepository,
    candle_fetcher: CandleFetcher,
    session_factory=SessionLocal,
    batch_size: int = 20,
    batch_sleep_seconds: float = 0.2,
) -> dict[str, object]:
    try:
        with session_factory() as db:
            tickers = universe_repo.list_universe_tickers(db, limit=20_000)
    except SQLAlchemyError as exc:
        return {
            "ok": False,
            "message": f"universe_load_failed:{exc}",
            "processed_count": 0,
            "failed_count": 0,
            "ticker_count": 0,
        }

    collector = CandleCollectionService(
        session_factory=session_factory,
        candle_repo=candle_repo,
        fetcher=candle_fetcher,
        now_fn=lambda: datetime.now(ZoneInfo(settings.server_timezone)),
    )
    chunk_size = max(batch_size, 1)
    chunks = [tickers[idx : idx + chunk_size] for idx in range(0, len(tickers), chunk_size)]
    inserted_total = 0
    updated_total = 0
    failed_count = 0
    processed = 0
    errors: list[str] = []

    for idx, chunk in enumerate(chunks):
        result = await collector.collect_incremental(tickers=chunk, timeframes=("1d",), source="post_market_backfill")
        inserted_total += int(result.get("inserted", 0))
        updated_total += int(result.get("updated", 0))
        failed_count += int(result.get("failed_count", 0))
        processed += int(result.get("processed_count", 0)) + int(result.get("failed_count", 0))
        for item in result.get("errors", []):
            if len(errors) >= 20:
                break
            errors.append(str(item))
        if batch_sleep_seconds > 0 and idx < len(chunks) - 1:
            await asyncio.sleep(batch_sleep_seconds)

    success_count = max(processed - failed_count, 0)
    success_rate = (success_count / processed) if processed > 0 else 1.0
    return {
        "ok": failed_count == 0,
        "message": "completed" if failed_count == 0 else f"partial:{failed_count}",
        "ticker_count": processed,
        "processed_count": processed,
        "failed_count": failed_count,
        "success_rate": round(success_rate, 4),
        "inserted": inserted_total,
        "updated": updated_total,
        "errors": errors,
    }


def _load_tracking_tickers(
    *,
    universe_repo: UniverseRepository,
    ordering_repo: OrderingRepository,
    session_factory=SessionLocal,
    maintenance_service: RuntimeMaintenanceService | None = None,
) -> list[str]:
    try:
        with session_factory() as db:
            trading_tickers = universe_repo.list_trading_tickers(db)
            tracking_tickers = set(universe_repo.list_tracking_tickers(db))
            universe_tickers = universe_repo.list_universe_tickers(db)
            open_positions = ordering_repo.list_open_positions(db)
    except SQLAlchemyError:
        return []

    for row in open_positions:
        ticker = str(getattr(row, "ticker", "")).strip()
        if ticker:
            tracking_tickers.add(ticker)

    merged = sorted(tracking_tickers)
    if maintenance_service is not None:
        maintenance_service.set_ticker_counts(
            trading=len(trading_tickers),
            tracking=len(merged),
            universe=len(universe_tickers),
        )
    return merged


def _load_tickers(
    *,
    universe_repo: UniverseRepository,
    ordering_repo: OrderingRepository,
    session_factory=SessionLocal,
    maintenance_service: RuntimeMaintenanceService | None = None,
) -> list[str]:
    # 하위호환: 기존 함수명 유지
    return _load_tracking_tickers(
        universe_repo=universe_repo,
        ordering_repo=ordering_repo,
        session_factory=session_factory,
        maintenance_service=maintenance_service,
    )


def _default_check_ticker() -> str:
    try:
        with SessionLocal() as db:
            tickers = UniverseRepository().list_trading_tickers(db)
            if tickers:
                return tickers[0]
    except SQLAlchemyError:
        pass
    return "005930"
