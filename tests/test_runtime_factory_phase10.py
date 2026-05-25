import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import ConfigManager
from app.repositories.candle import CandleRepository
from app.repositories.ordering import OrderingRepository
from app.repositories.universe import UniverseRepository
from app.risk.engine import RiskEngine
from app.services.runtime_factory import DbAtrProvider, build_runtime_bundle
from app.services.runtime_safety import RuntimeSafetyManager
from app.services.runtime_state import RuntimeState
from tests.utils import build_session_factory


def test_build_runtime_bundle_constructs_real_components():
    bundle = build_runtime_bundle(
        config=ConfigManager(),
        safety=RuntimeSafetyManager(runtime=RuntimeState()),
    )
    assert bundle.coordinator is not None
    assert bundle.queue is not None
    assert bundle.maintenance_service is not None


class FakeKiwoomClient:
    async def post(self, *, path: str, api_id: str, payload: dict[str, Any], is_order: bool) -> dict[str, Any]:  # noqa: ARG002
        if api_id == "ka10001":
            return {"output": {"stck_prpr": "70000"}}
        return {"output": []}


def test_build_runtime_bundle_live_mode_wires_live_providers():
    maker = build_session_factory()
    bundle = build_runtime_bundle(
        config=ConfigManager(),
        safety=RuntimeSafetyManager(runtime=RuntimeState()),
        trading_mode="live",
        session_factory=maker,
        kiwoom_client=FakeKiwoomClient(),  # type: ignore[arg-type]
    )
    loop_a = bundle.coordinator.loop_a
    loop_b = bundle.coordinator.loop_b
    assert loop_a.price_provider.__class__.__name__ == "LivePriceProvider"
    assert loop_b.candle_fetcher.__class__.__name__ == "ResilientCandleFetcher"


def test_build_runtime_bundle_paper_mode_also_uses_live_market_data():
    maker = build_session_factory()
    bundle = build_runtime_bundle(
        config=ConfigManager(),
        safety=RuntimeSafetyManager(runtime=RuntimeState()),
        trading_mode="paper",
        session_factory=maker,
        kiwoom_client=FakeKiwoomClient(),  # type: ignore[arg-type]
    )
    loop_a = bundle.coordinator.loop_a
    loop_b = bundle.coordinator.loop_b
    assert loop_a.price_provider.__class__.__name__ == "LivePriceProvider"
    assert loop_b.candle_fetcher.__class__.__name__ == "ResilientCandleFetcher"


def test_build_runtime_bundle_tracking_tickers_include_blocked_active_and_open_positions():
    maker = build_session_factory()
    universe_repo = UniverseRepository()
    ordering_repo = OrderingRepository()
    with maker() as db:
        universe_repo.upsert_symbol(
            db,
            ticker="005930",
            name="Samsung",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=False,
            status="normal",
        )
        universe_repo.upsert_symbol(
            db,
            ticker="000660",
            name="SK",
            market="KOSPI200",
            in_universe=True,
            is_active=True,
            is_blocked=True,
            status="normal",
        )
        universe_repo.upsert_symbol(
            db,
            ticker="035420",
            name="Naver",
            market="KOSPI200",
            in_universe=True,
            is_active=False,
            is_blocked=False,
            status="normal",
        )
        ordering_repo.open_position(
            db,
            order_id=None,
            ticker="035420",
            strategy_id="1",
            entry_price=100.0,
            stop_price=95.0,
            take_profit_price=110.0,
            quantity=1.0,
        )
    bundle = build_runtime_bundle(
        config=ConfigManager(),
        safety=RuntimeSafetyManager(runtime=RuntimeState()),
        trading_mode="paper",
        session_factory=maker,
    )
    tracking = bundle.coordinator.tickers_provider()
    assert tracking == ["000660", "005930", "035420"]
    metrics = bundle.coordinator.health_snapshot()
    ticker_counts = metrics["ticker_counts"]
    assert ticker_counts["trading"] == 1
    assert ticker_counts["tracking"] == 3
    assert ticker_counts["universe"] == 3


def test_db_atr_provider_uses_session_factory():
    maker = build_session_factory()
    repo = CandleRepository()
    ticker = "005930"
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    with maker() as db:
        for i in range(20):
            ts = base + timedelta(minutes=5 * i)
            repo.upsert_incremental(
                db,
                ticker=ticker,
                timeframe="5m",
                candle_time=ts,
                open_price=100 + i,
                high=101 + i,
                low=99 + i,
                close=100 + i,
                volume=1000 + i,
            )

    provider = DbAtrProvider(repo=repo, risk_engine=RiskEngine(), session_factory=maker)
    atr = asyncio.run(provider.get_atr(ticker=ticker, strategy_id="1"))
    assert atr >= 1.0
