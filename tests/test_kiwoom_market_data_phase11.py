import asyncio
from datetime import datetime, timezone
from typing import Any

from app.integrations.kiwoom.market_data import KiwoomMarketDataGateway


class FakeClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    async def post(self, *, path: str, api_id: str, payload: dict[str, Any], is_order: bool) -> dict[str, Any]:
        self.calls.append(
            {"path": path, "api_id": api_id, "payload": payload, "is_order": is_order}
        )
        return self.responses.pop(0)


def test_kiwoom_market_data_current_price_parse():
    client = FakeClient([{"output": {"stck_prpr": "70,100"}}])
    gateway = KiwoomMarketDataGateway(client)
    price = asyncio.run(gateway.get_current_price("005930"))
    assert price == 70100.0
    assert client.calls[0]["api_id"] == "ka10001"


def test_kiwoom_market_data_current_price_parse_cur_prc_field():
    client = FakeClient([{"cur_prc": "+207000"}])
    gateway = KiwoomMarketDataGateway(client)
    price = asyncio.run(gateway.get_current_price("005930"))
    assert price == 207000.0


def test_kiwoom_market_data_fetch_incremental_filters_since():
    client = FakeClient(
        [
            {
                "output": [
                    {
                        "stck_bsop_date": "20260101",
                        "stck_cntg_hour": "090000",
                        "stck_oprc": "100",
                        "stck_hgpr": "102",
                        "stck_lwpr": "99",
                        "stck_clpr": "101",
                        "acml_vol": "1000",
                    },
                    {
                        "stck_bsop_date": "20260101",
                        "stck_cntg_hour": "090500",
                        "stck_oprc": "101",
                        "stck_hgpr": "103",
                        "stck_lwpr": "100",
                        "stck_clpr": "102",
                        "acml_vol": "1200",
                    },
                ]
            }
        ]
    )
    gateway = KiwoomMarketDataGateway(client)
    since = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    candles = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="5m", since=since))
    assert len(candles) == 1
    assert candles[0].close == 102.0
    assert client.calls[0]["api_id"] == "ka10080"


def test_kiwoom_market_data_minute_request_has_required_fields():
    client = FakeClient([{"output": []}])
    gateway = KiwoomMarketDataGateway(client)
    candles = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="5m", since=None))
    assert candles == []
    call = client.calls[0]
    assert call["api_id"] == "ka10080"
    assert call["payload"]["stk_cd"] == "005930_AL"
    assert call["payload"]["tic_scope"] == "5"
    assert call["payload"]["upd_stkpc_tp"] == "1"
    assert len(call["payload"]["base_dt"]) == 8
    assert call["payload"]["base_dt"].isdigit()


def test_kiwoom_market_data_three_minute_request_has_required_fields():
    client = FakeClient([{"output": []}])
    gateway = KiwoomMarketDataGateway(client)
    candles = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="3m", since=None))
    assert candles == []
    call = client.calls[0]
    assert call["api_id"] == "ka10080"
    assert call["payload"]["stk_cd"] == "005930_AL"
    assert call["payload"]["tic_scope"] == "3"
    assert call["payload"]["upd_stkpc_tp"] == "1"


def test_kiwoom_market_data_unsupported_timeframe_raises():
    client = FakeClient([{"output": []}])
    gateway = KiwoomMarketDataGateway(client)
    try:
        asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="2m", since=None))
    except ValueError as exc:
        assert "unsupported timeframe" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_kiwoom_market_data_daily_request_has_required_fields():
    client = FakeClient([{"output": []}])
    gateway = KiwoomMarketDataGateway(client)
    since = datetime(2026, 1, 8, 9, 0, tzinfo=timezone.utc)
    candles = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="1d", since=since))
    assert candles == []
    call = client.calls[0]
    assert call["api_id"] == "ka10081"
    assert call["payload"]["stk_cd"] == "005930_AL"
    assert call["payload"]["base_dt"] == "20260108"
    assert call["payload"]["upd_stkpc_tp"] == "1"


def test_kiwoom_market_data_parses_official_minute_response_fields():
    client = FakeClient(
        [
            {
                "stk_min_pole_chart_qry": [
                    {
                        "cntr_tm": "20260202100500",
                        "open_pric": "-78850",
                        "high_pric": "-78900",
                        "low_pric": "-78800",
                        "cur_prc": "-78800",
                        "trde_qty": "7913",
                    }
                ]
            }
        ]
    )
    gateway = KiwoomMarketDataGateway(client)
    candles = asyncio.run(gateway.fetch_candles_incremental(ticker="005930", timeframe="5m", since=None))
    assert len(candles) == 1
    assert candles[0].open == 78850.0
    assert candles[0].high == 78900.0
    assert candles[0].low == 78800.0
    assert candles[0].close == 78800.0
    assert candles[0].volume == 7913.0
