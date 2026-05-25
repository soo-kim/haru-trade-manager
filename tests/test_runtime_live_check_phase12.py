import asyncio
from typing import Any

from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings
from app.integrations.kiwoom.client import KiwoomApiClient
from app.services.runtime_factory import run_live_connectivity_check


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses

    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:  # noqa: ARG002
        return self.responses.pop(0)


def test_live_connectivity_check_reports_auth_error_without_credentials():
    original_mode = settings.trading_mode
    settings.trading_mode = "paper"
    try:
        result = asyncio.run(run_live_connectivity_check())
        assert result["ok"] is False
        assert result["enabled"] is True
        assert result["trading_mode"] == "paper"
        assert result["token_ok"] is False
    finally:
        settings.trading_mode = original_mode


def test_live_connectivity_check_success_like_response():
    original_mode = settings.trading_mode
    settings.trading_mode = "live"
    client = KiwoomApiClient(
        RateLimitedClient(min_interval=0.0),
        base_url="https://example.test",
        app_key="key",
        app_secret="secret",
        transport=FakeTransport(
            [
                {"access_token": "t-1", "expires_in": 3600},
                {"output": {"stck_prpr": "70100", "trd_tm": "090001"}},  # server time probe
                {"output": {"stck_prpr": "70100"}},  # price probe
            ]
        ),
        token_retry_backoff=(0, 0, 0),
    )
    try:
        result = asyncio.run(run_live_connectivity_check(kiwoom_client=client, ticker="005930"))
        assert result["enabled"] is True
        assert result["token_ok"] is True
        assert result["server_time_ok"] is True
        assert result["price_ok"] is True
        assert result["price"] == 70100.0
        assert result["trading_mode"] == "live"
    finally:
        settings.trading_mode = original_mode
