from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.models import Candle
from app.integrations.kiwoom.client import KiwoomApiClient
from app.integrations.kiwoom.schema import build_datetime, first_list, first_non_empty, parse_dt_any, parse_float, parse_price


class KiwoomMarketDataGateway:
    """
    Kiwoom REST market-data adapter.
    The payload/response schema may vary by account/API version, so parser is defensive.
    """

    def __init__(self, client: KiwoomApiClient) -> None:
        self.client = client

    async def get_current_price(self, ticker: str) -> float:
        payload = {"stk_cd": self._with_suffix(ticker)}
        data = await self.client.post(
            path="/api/dostk/stkinfo",
            api_id="ka10001",
            payload=payload,
            is_order=False,
        )
        value = first_non_empty(data, ["cur_prc", "prpr", "stck_prpr", "current_price", "last_price"])
        parsed = parse_price(value)
        if parsed is not None:
            return parsed
        return 0.0

    async def fetch_candles_incremental(
        self,
        *,
        ticker: str,
        timeframe: str,
        since: datetime | None,
    ) -> list[Candle]:
        path, api_id, payload = self._build_chart_request(ticker=ticker, timeframe=timeframe, since=since)
        data = await self.client.post(
            path=path,
            api_id=api_id,
            payload=payload,
            is_order=False,
        )
        rows = first_list(
            data,
            ["candles", "output", "output1", "stk_min_pole_chart_qry", "stk_dt_pole_chart_qry", "items", "rows"],
        )

        candles: list[Candle] = []
        for row in rows:
            ts = self._parse_row_time(row)
            if ts is None:
                continue
            if since is not None and ts <= since:
                continue
            open_price = parse_price(first_non_empty(row, ["open", "open_pric", "stck_oprc"])) or 0.0
            high_price = parse_price(first_non_empty(row, ["high", "high_pric", "stck_hgpr"])) or 0.0
            low_price = parse_price(first_non_empty(row, ["low", "low_pric", "stck_lwpr"])) or 0.0
            close_price = parse_price(first_non_empty(row, ["close", "cur_prc", "stck_clpr", "stck_prpr"])) or 0.0
            canonical_high = max(open_price, high_price, low_price, close_price)
            canonical_low = min(open_price, high_price, low_price, close_price)
            parsed = Candle(
                open=open_price,
                high=canonical_high,
                low=canonical_low,
                close=close_price,
                volume=parse_float(first_non_empty(row, ["volume", "trde_qty", "acml_vol", "acc_trde_qty"])) or 0.0,
                ts=ts,
            )
            candles.append(parsed)
        candles.sort(key=lambda x: x.ts)
        return candles

    def _build_chart_request(
        self,
        *,
        ticker: str,
        timeframe: str,
        since: datetime | None,
    ) -> tuple[str, str, dict[str, Any]]:
        suffix = self._with_suffix(ticker)
        if timeframe == "1d":
            payload = {
                "stk_cd": suffix,
                "base_dt": self._fmt_date(since),
                "upd_stkpc_tp": "1",
            }
            return "/api/dostk/chart", "ka10081", payload

        minute_map = {"3m": "3", "5m": "5", "15m": "15", "60m": "60"}
        scope = minute_map.get(timeframe)
        if scope is None:
            raise ValueError(f"unsupported timeframe: {timeframe}")
        payload = {
            "stk_cd": suffix,
            "tic_scope": scope,
            "base_dt": self._fmt_date(since),
            "upd_stkpc_tp": "1",
        }
        return "/api/dostk/chart", "ka10080", payload

    @staticmethod
    def _with_suffix(ticker: str) -> str:
        return f"{ticker}_AL"

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.replace(",", "").strip()
            if text == "":
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _parse_row_time(row: dict[str, Any]) -> datetime | None:
        if (raw := first_non_empty(row, ["candle_time", "datetime", "timestamp", "cntr_tm", "dt"], deep=False)) is not None:
            parsed = parse_dt_any(raw)
            if parsed is not None:
                return parsed

        date_part = first_non_empty(row, ["stck_bsop_date", "date", "dt"], deep=False)
        time_part = first_non_empty(row, ["stck_cntg_hour", "time", "tm"], deep=False)
        return build_datetime(date_part, time_part)

    @staticmethod
    def _fmt_date(value: datetime | None) -> str:
        if value is None:
            return datetime.now(KiwoomMarketDataGateway._KST).strftime("%Y%m%d")
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(KiwoomMarketDataGateway._KST).strftime("%Y%m%d")
    _KST = timezone(timedelta(hours=9))
