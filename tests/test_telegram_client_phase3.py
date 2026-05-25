import asyncio
from typing import Any

from app.core.rate_limited_client import RateLimitedClient
from app.integrations.telegram.client import TelegramClient


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        self.calls.append({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        return {"ok": True}


def test_telegram_send_message_success():
    transport = FakeTransport()
    client = TelegramClient(
        RateLimitedClient(min_interval=0.0),
        token="bot-token",
        chat_id="1234",
        transport=transport,
    )
    ok = asyncio.run(client.send_message("hello"))
    assert ok is True
    assert len(transport.calls) == 1
    assert transport.calls[0]["payload"]["chat_id"] == "1234"


def test_telegram_send_message_disabled_without_credentials():
    transport = FakeTransport()
    client = TelegramClient(
        RateLimitedClient(min_interval=0.0),
        token="",
        chat_id="",
        transport=transport,
    )
    ok = asyncio.run(client.send_message("hello"))
    assert ok is False
    assert transport.calls == []
