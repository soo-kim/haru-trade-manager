from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Any, Protocol

from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings


class JsonPostTransport(Protocol):
    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        raise NotImplementedError


class UrllibTelegramTransport:
    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            req = urllib.request.Request(
                url=url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))

        return await asyncio.to_thread(_call)


class TelegramClient:
    def __init__(
        self,
        rate_client: RateLimitedClient,
        *,
        token: str | None = None,
        chat_id: str | None = None,
        transport: JsonPostTransport | None = None,
        timeout: int = 10,
    ) -> None:
        self.rate_client = rate_client
        self.token = token if token is not None else settings.telegram_token
        self.chat_id = chat_id if chat_id is not None else settings.telegram_chat_id
        self.transport = transport or UrllibTelegramTransport()
        self.timeout = timeout

    async def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        headers = {"Content-Type": "application/json"}

        async def _send() -> bool:
            result = await self.transport.post(url, payload, headers, self.timeout)
            return bool(result.get("ok", True))

        try:
            return await self.rate_client.submit(_send, is_order=False)
        except Exception:  # noqa: BLE001
            return False
