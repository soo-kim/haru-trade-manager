import asyncio
from datetime import datetime, timedelta, timezone

import app.main as main_module
from app.core.settings import settings
from app.domain.models import Candle


class _FakeRateLimitedClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass


class _FakeKiwoomClient:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        pass

    async def ensure_token(self) -> str:
        return "fake-token"


class _FakeMarketDataGateway:
    def __init__(self, client) -> None:  # noqa: ANN001
        self.client = client

    async def fetch_candles_incremental(self, *, ticker: str, timeframe: str, since):  # noqa: ANN001
        del ticker, since
        step_minutes = {"1d": 24 * 60, "60m": 60, "15m": 15, "5m": 5, "3m": 3}
        count_map = {"1d": 240, "60m": 240, "15m": 240, "5m": 400, "3m": 240}
        base = datetime(2026, 1, 2, 9, 0, tzinfo=timezone.utc)
        count = count_map[timeframe]
        step = step_minutes[timeframe]
        return [
            Candle(
                open=100.0 + idx,
                high=101.0 + idx,
                low=99.0 + idx,
                close=100.5 + idx,
                volume=1000.0 + idx,
                ts=base + timedelta(minutes=step * idx),
            )
            for idx in range(count)
        ]


def test_bootstrap_candles_stores_all_fetched_without_cap(monkeypatch):
    monkeypatch.setattr(main_module, "RateLimitedClient", _FakeRateLimitedClient)
    monkeypatch.setattr(main_module, "KiwoomApiClient", _FakeKiwoomClient)
    monkeypatch.setattr(main_module, "KiwoomMarketDataGateway", _FakeMarketDataGateway)

    original_environment = settings.environment
    original_key = settings.kiwoom_app_key
    original_secret = settings.kiwoom_app_secret
    settings.environment = "local"
    settings.kiwoom_app_key = "dummy-key"
    settings.kiwoom_app_secret = "dummy-secret"
    try:
        status = asyncio.run(main_module._bootstrap_candles_on_first_run(tickers=["999999"]))
    finally:
        settings.environment = original_environment
        settings.kiwoom_app_key = original_key
        settings.kiwoom_app_secret = original_secret

    assert status["ok"] is True
    assert status["errors"] == []

    expected_per_timeframe = {"1d": 240, "3m": 240, "5m": 400, "15m": 240, "60m": 240}
    expected_total = sum(expected_per_timeframe.values())
    assert status["candles_inserted"] == expected_total
    assert status["candles_updated"] == 0

    timeframe_stats = status["timeframe_stats"]
    for timeframe, expected in expected_per_timeframe.items():
        assert timeframe_stats[timeframe]["inserted"] == expected
        assert timeframe_stats[timeframe]["updated"] == 0
        assert timeframe_stats[timeframe]["tickers_with_data"] == 1
