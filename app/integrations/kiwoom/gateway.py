from __future__ import annotations

from datetime import datetime, timezone

from app.core.settings import settings
from app.domain.models import OrderRequest, OrderResult, OrderStatus
from app.integrations.kiwoom.client import KiwoomApiClient
from app.integrations.kiwoom.schema import build_datetime, first_list, first_non_empty, parse_dt_any, parse_float


class KiwoomOrderGateway:
    """
    Kiwoom REST adapter used by OrderService.
    """

    def __init__(self, client: KiwoomApiClient, *, account_no: str | None = None) -> None:
        self.client = client
        self.account_no = account_no or settings.kiwoom_account_no

    @staticmethod
    def _with_suffix(ticker: str) -> str:
        return f"{ticker}_AL"

    async def place_order(self, req: OrderRequest) -> OrderResult:
        if not self.account_no:
            return OrderResult(ok=False, order_id=None, error="KIWOOM_ACCOUNT_NO is required")

        if req.side not in {"buy", "sell"}:
            return OrderResult(ok=False, order_id=None, error=f"unsupported side: {req.side}")

        api_id = "kt10000" if req.side == "buy" else "kt10001"
        payload = {
            "acc_no": self.account_no,
            "dmst_stex_tp": "KRX",
            "stk_cd": self._with_suffix(req.ticker),
            "ord_qty": int(req.qty),
            "ord_uv": int(req.price or 0),
            "trde_tp": "3" if req.order_type == "market" else "0",
        }
        data = await self.client.post(path="/api/dostk/ordr", api_id=api_id, payload=payload, is_order=True)
        order_id = first_non_empty(data, ["ord_no", "order_no", "odno"])
        code = str(first_non_empty(data, ["return_code", "rt_cd", "code"]) or "0")
        message = first_non_empty(data, ["return_msg", "msg1", "message"])
        ok = code in {"0", "None"} and bool(order_id)
        return OrderResult(ok=ok, order_id=str(order_id) if order_id else None, error=None if ok else str(message or "order_failed"))

    async def get_order_status(self, order_id: str) -> OrderStatus:
        if not self.account_no:
            return OrderStatus(exists=False, status="missing_account")

        payload = {
            "acc_no": self.account_no,
            "dmst_stex_tp": "KRX",
            "qry_tp": "1",
            "stk_cd": "",
            "ord_no": order_id,
        }
        data = await self.client.post(path="/api/dostk/acnt", api_id="ka10075", payload=payload, is_order=False)
        rows = first_list(data, ["stk_unexp_trde_opt_data_qry", "acnt_ord_cntr_prps_dtl", "orders"])
        if not rows:
            return OrderStatus(exists=False, status="not_found")
        row = rows[0]
        status = str(first_non_empty(row, ["ord_stts", "ord_gb", "status"]) or "accepted").lower()
        filled = parse_float(first_non_empty(row, ["cntr_qty", "filled_qty", "exec_qty"])) or 0.0
        return OrderStatus(exists=True, status=status, filled_qty=filled)

    async def get_server_time(self) -> datetime:
        payload = {"stk_cd": "005930_AL"}
        data = await self.client.post(path="/api/dostk/stkinfo", api_id="ka10001", payload=payload, is_order=False)
        timestamp = first_non_empty(data, ["server_time", "trd_tm", "stck_cntg_hour", "time"])
        parsed = parse_dt_any(timestamp)
        if parsed is not None:
            return parsed

        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        from_parts = build_datetime(today, timestamp)
        if from_parts is not None:
            return from_parts
        return datetime.now(timezone.utc)
