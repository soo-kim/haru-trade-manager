import asyncio

from app.integrations.kiwoom.gateway import OrderRequest
from app.integrations.kiwoom.real_gateway import RealKiwoomGateway


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def post(self, path, api_id, payload, is_order=False):  # noqa: ANN001
        self.calls.append((path, api_id, payload, is_order))
        return self.responses.pop(0)


def test_place_order_parses_success():
    client = FakeClient([{"return_code": "0", "ord_no": "12345"}])
    gateway = RealKiwoomGateway(client, account_no="111122223333")
    req = OrderRequest(ticker="005930", side="buy", order_type="limit", quantity=1, price=70000)
    result = asyncio.run(gateway.place_order(req))
    assert result.ok is True
    assert result.order_id == "12345"
    assert client.calls[0][1] == "kt10000"


def test_get_order_status_not_found():
    client = FakeClient([{"stk_unexp_trde_opt_data_qry": []}])
    gateway = RealKiwoomGateway(client, account_no="111122223333")
    status = asyncio.run(gateway.get_order_status("12345"))
    assert status.exists is False
    assert status.status == "not_found"
