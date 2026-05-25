import asyncio
from datetime import datetime, timezone
from typing import Any

from app.domain.models import OrderRequest
from app.integrations.kiwoom.gateway import KiwoomOrderGateway


class FakeApiClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def post(self, *, path: str, api_id: str, payload: dict[str, Any], is_order: bool) -> dict[str, Any]:
        self.calls.append(
            {
                "path": path,
                "api_id": api_id,
                "payload": payload,
                "is_order": is_order,
            }
        )
        return self.responses.pop(0)


def test_place_order_success_maps_fields():
    client = FakeApiClient([{"return_code": "0", "ord_no": "ORD-1"}])
    gateway = KiwoomOrderGateway(client, account_no="1234567890")
    req = OrderRequest(ticker="005930", side="buy", order_type="limit", qty=2, price=70000)

    result = asyncio.run(gateway.place_order(req))
    assert result.ok is True
    assert result.order_id == "ORD-1"
    assert client.calls[0]["api_id"] == "kt10000"
    assert client.calls[0]["payload"]["stk_cd"] == "005930_AL"


def test_get_order_status_not_found_and_server_time_fallback():
    client = FakeApiClient(
        [
            {"stk_unexp_trde_opt_data_qry": []},
            {},
        ]
    )
    gateway = KiwoomOrderGateway(client, account_no="1234567890")

    status = asyncio.run(gateway.get_order_status("ORD-1"))
    assert status.exists is False
    assert status.status == "not_found"

    server_time = asyncio.run(gateway.get_server_time())
    assert isinstance(server_time, datetime)
    assert server_time.tzinfo == timezone.utc
