from __future__ import annotations

import json
import urllib.request

from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings


class TelegramClient:
    def __init__(self, rate_client: RateLimitedClient) -> None:
        self.rate_client = rate_client
        self.token = settings.telegram_token
        self.chat_id = settings.telegram_chat_id

    async def send_message(self, text: str) -> bool:
        if not self.token or not self.chat_id:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        headers = {"Content-Type": "application/json"}

        async def do_request() -> bool:
            req = urllib.request.Request(
                url=url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as _:
                return True

        return await self.rate_client.enqueue(do_request, is_order=False)
