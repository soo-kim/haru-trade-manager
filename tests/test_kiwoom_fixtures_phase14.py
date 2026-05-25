import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.models import OrderRequest
from app.integrations.kiwoom.gateway import KiwoomOrderGateway
from app.integrations.kiwoom.market_data import KiwoomMarketDataGateway


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kiwoom"


def _load(name: str) -> dict[str, Any]:
    with (FIXTURE_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


class FakeApiClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses

    async def post(self, *, path: str, api_id: str, payload: dict[str, Any], is_order: bool) -> dict[str, Any]:  # noqa: ARG002
        return self.responses.pop(0)


def test_gateway_parses_order_place_and_status_from_fixtures():
    client = FakeApiClient(
        [
            _load("order_place_output.json"),
            _load("order_status_output2.json"),
        ]
    )
    gateway = KiwoomOrderGateway(client, account_no="1234567890")

    req = OrderRequest(ticker="005930", side="buy", order_type="limit", qty=1, price=70000)
    placed = asyncio.run(gateway.place_order(req))
    assert placed.ok is True
    assert placed.order_id == "ORD-999"

    status = asyncio.run(gateway.get_order_status("ORD-999"))
    assert status.exists is True
    assert status.status == "filled"
    assert status.filled_qty == 1234.0


def test_gateway_parses_server_time_hhmmss_fixture():
    client = FakeApiClient([_load("stkinfo_hhmmss.json")])
    gateway = KiwoomOrderGateway(client, account_no="1234567890")
    server_time = asyncio.run(gateway.get_server_time())
    assert isinstance(server_time, datetime)
    assert server_time.tzinfo == timezone.utc
    assert server_time.hour == 15
    assert server_time.minute == 45
    assert server_time.second == 33


def test_market_data_parses_price_and_candles_from_fixtures():
    client = FakeApiClient(
        [
            _load("stkinfo_output.json"),
            _load("candles_output.json"),
            _load("candles_output1_rows.json"),
            _load("stkinfo_flat.json"),
        ]
    )
    gateway = KiwoomMarketDataGateway(client)

    price_nested = asyncio.run(gateway.get_current_price("005930"))
    assert price_nested == 70100.0

    since = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    candles = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="5m", since=since))
    assert len(candles) == 1
    assert candles[0].close == 102.0

    candles_rows = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="5m", since=None))
    assert len(candles_rows) == 1
    assert candles_rows[0].open == 103.0

    price_flat = asyncio.run(gateway.get_current_price("005930"))
    assert price_flat == 70200.0
