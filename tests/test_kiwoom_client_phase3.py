import asyncio
from typing import Any

from app.core.rate_limited_client import RateLimitedClient
from app.integrations.kiwoom.client import KiwoomApiClient


class FakeTransport:
    def __init__(self, responses: list[dict[str, Any] | Exception]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        self.calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_kiwoom_client_refreshes_token_then_calls_api():
    transport = FakeTransport(
        [
            {"access_token": "token-1", "expires_in": 3600},
            {"return_code": "0", "value": "ok"},
        ]
    )
    client = KiwoomApiClient(
        RateLimitedClient(min_interval=0.0),
        base_url="https://example.test",
        app_key="key",
        app_secret="secret",
        transport=transport,
        token_retry_backoff=(0, 0, 0),
    )

    result = asyncio.run(client.post(path="/api/test", api_id="ka0001", payload={"a": 1}, is_order=False))
    assert result["value"] == "ok"
    assert transport.calls[0]["url"] == "https://example.test/oauth2/token"
    assert transport.calls[1]["headers"]["authorization"] == "Bearer token-1"
    assert transport.calls[1]["headers"]["api-id"] == "ka0001"


def test_kiwoom_client_token_refresh_retries_three_times():
    transport = FakeTransport(
        [
            RuntimeError("fail-1"),
            RuntimeError("fail-2"),
            {"token": "token-3", "expires_in": 300},
        ]
    )
    client = KiwoomApiClient(
        RateLimitedClient(min_interval=0.0),
        base_url="https://example.test",
        app_key="key",
        app_secret="secret",
        transport=transport,
        token_retry_backoff=(0, 0, 0),
    )

    token = asyncio.run(client.refresh_token())
    assert token == "token-3"
    assert len(transport.calls) == 3
