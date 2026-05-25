from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings

logger = logging.getLogger(__name__)


class KiwoomRestClient:
    def __init__(self, rate_client: RateLimitedClient) -> None:
        self.rate_client = rate_client
        self.base_url = settings.kiwoom_base_url.rstrip("/")
        self.app_key = settings.kiwoom_app_key
        self.app_secret = settings.kiwoom_app_secret
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def _needs_refresh(self) -> bool:
        if not self._token or not self._expires_at:
            return True
        return datetime.now(timezone.utc) >= (self._expires_at - timedelta(minutes=5))

    async def _http_post(
        self,
        path: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        is_order: bool,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"

        async def do_request() -> dict[str, Any]:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url=url, data=body, method="POST")
            for k, v in headers.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))

        return await self.rate_client.enqueue(do_request, is_order=is_order)

    async def ensure_token(self) -> str:
        if not self._needs_refresh():
            return self._token or ""

        if not self.app_key or not self.app_secret:
            raise RuntimeError("KIWOOM_APP_KEY / KIWOOM_APP_SECRET is required for live mode")

        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret,
        }
        headers = {"Content-Type": "application/json;charset=UTF-8"}

        backoff = 1.0
        last_error: Exception | None = None
        for _ in range(3):
            try:
                data = await self._http_post("/oauth2/token", payload, headers, is_order=False)
                token = data.get("token") or data.get("access_token")
                if not token:
                    raise RuntimeError(f"token missing from response: {data}")
                expires_dt = data.get("expires_dt")
                if expires_dt:
                    self._expires_at = datetime.strptime(expires_dt, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                else:
                    expires_in = int(data.get("expires_in", 3600))
                    self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
                self._token = token
                await self.rate_client.set_token(token, int((self._expires_at - datetime.now(timezone.utc)).total_seconds()))
                return token
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                await asyncio.sleep(backoff)
                backoff *= 2
        raise RuntimeError(f"kiwoom token refresh failed: {last_error}")

    async def post(
        self,
        path: str,
        api_id: str,
        payload: dict[str, Any],
        is_order: bool = False,
    ) -> dict[str, Any]:
        token = await self.ensure_token()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "cont-yn": "N",
            "next-key": "",
            "api-id": api_id,
        }
        try:
            return await self._http_post(path, payload, headers, is_order=is_order)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            logger.error("kiwoom http error: %s body=%s", exc.code, body)
            raise
