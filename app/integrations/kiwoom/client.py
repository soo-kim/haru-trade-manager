from __future__ import annotations

import asyncio
import json
import urllib.request
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Protocol
from typing import Any

from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings


class JsonHttpTransport(Protocol):
    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        raise NotImplementedError


class UrllibJsonTransport:
    async def post(self, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            req = urllib.request.Request(
                url=url,
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
            )
            for k, v in headers.items():
                req.add_header(k, v)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))

        return await asyncio.to_thread(_call)


class KiwoomApiClient:
    def __init__(
        self,
        rate_client: RateLimitedClient,
        *,
        base_url: str | None = None,
        app_key: str | None = None,
        app_secret: str | None = None,
        transport: JsonHttpTransport | None = None,
        timeout: int = 10,
        token_retry_backoff: Sequence[float] = (1.0, 2.0, 4.0),
    ) -> None:
        self.rate_client = rate_client
        self.base_url = (base_url or settings.kiwoom_base_url).rstrip("/")
        self.app_key = app_key if app_key is not None else settings.kiwoom_app_key
        self.app_secret = app_secret if app_secret is not None else settings.kiwoom_app_secret
        self.transport = transport or UrllibJsonTransport()
        self.timeout = timeout
        self.token_retry_backoff = list(token_retry_backoff)
        self._token: str | None = None
        self._expires_at: datetime | None = None

    def token_expiring(self) -> bool:
        if not self._token or not self._expires_at:
            return True
        return datetime.now(timezone.utc) >= (self._expires_at - timedelta(minutes=5))

    async def _post_with_rate_limit(
        self, *, url: str, payload: dict[str, Any], headers: dict[str, str], is_order: bool
    ) -> dict[str, Any]:
        return await self.rate_client.submit(
            lambda: self.transport.post(url, payload, headers, self.timeout),
            is_order=is_order,
        )

    async def refresh_token(self) -> str:
        if not self.app_key or not self.app_secret:
            raise RuntimeError("KIWOOM_APP_KEY and KIWOOM_APP_SECRET are required")
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "secretkey": self.app_secret,
        }
        headers = {"Content-Type": "application/json;charset=UTF-8"}
        data: dict[str, Any] | None = None
        last_error: Exception | None = None
        for index, backoff in enumerate(self.token_retry_backoff):
            try:
                data = await self._post_with_rate_limit(
                    url=f"{self.base_url}/oauth2/token",
                    payload=payload,
                    headers=headers,
                    is_order=False,
                )
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if index < len(self.token_retry_backoff) - 1:
                    await asyncio.sleep(backoff)
        if data is None:
            raise RuntimeError(f"kiwoom token refresh failed: {last_error}")

        token = data.get("token") or data.get("access_token")
        if not token:
            raise RuntimeError(f"token not found in response: {data}")
        self._token = token
        expires_dt = data.get("expires_dt")
        if expires_dt:
            self._expires_at = datetime.strptime(expires_dt, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        else:
            expires_in = int(data.get("expires_in", 3600))
            self._expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        return token

    async def ensure_token(self) -> str:
        if self.token_expiring():
            await self.refresh_token()
            if self._token and self._expires_at:
                expires_in = int(max((self._expires_at - datetime.now(timezone.utc)).total_seconds(), 0))
                await self.rate_client.set_token(self._token, expires_in)
        return self._token or ""

    async def post(self, *, path: str, api_id: str, payload: dict[str, Any], is_order: bool) -> dict[str, Any]:
        token = await self.ensure_token()
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "cont-yn": "N",
            "next-key": "",
            "api-id": api_id,
        }
        return await self._post_with_rate_limit(
            url=f"{self.base_url}{path}",
            payload=payload,
            headers=headers,
            is_order=is_order,
        )
