from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.kiwoom.gateway import KiwoomGateway, OrderRequest, OrderResult, OrderStatus
from app.integrations.kiwoom.rest_client import KiwoomRestClient


class RealKiwoomGateway(KiwoomGateway):
    def __init__(self, client: KiwoomRestClient, account_no: str) -> None:
        self.client = client
        self.account_no = account_no

    @staticmethod
    def _with_suffix(ticker: str) -> str:
        return f"{ticker}_AL"

    async def place_order(self, request: OrderRequest) -> OrderResult:
        api_id = "kt10000" if request.side == "buy" else "kt10001"
        payload = {
            "acc_no": self.account_no,
            "dmst_stex_tp": "KRX",
            "stk_cd": self._with_suffix(request.ticker),
            "ord_qty": int(request.quantity),
            "ord_uv": int(request.price or 0),
            "trde_tp": "3" if request.order_type == "market" else "0",
        }
        data = await self.client.post("/api/dostk/ordr", api_id=api_id, payload=payload, is_order=True)
        order_id = data.get("ord_no")
        code = str(data.get("return_code", "0"))
        ok = code in {"0", "None"} and bool(order_id)
        return OrderResult(ok=ok, order_id=order_id, error=None if ok else data.get("return_msg"))

    async def get_order_status(self, order_id: str) -> OrderStatus:
        payload = {
            "acc_no": self.account_no,
            "dmst_stex_tp": "KRX",
            "qry_tp": "1",
            "stk_cd": "",
            "ord_no": order_id,
        }
        data = await self.client.post("/api/dostk/acnt", api_id="ka10075", payload=payload, is_order=False)
        rows = data.get("stk_unexp_trde_opt_data_qry") or data.get("acnt_ord_cntr_prps_dtl") or []
        if not rows:
            return OrderStatus(exists=False, status="not_found", filled_quantity=0.0)
        row = rows[0]
        status = str(row.get("ord_stts", row.get("ord_gb", "accepted"))).lower()
        filled = float(row.get("cntr_qty", row.get("filled_qty", 0)) or 0.0)
        return OrderStatus(exists=True, status=status, filled_quantity=filled)

    async def get_server_time(self) -> datetime:
        # 별도 서버시간 API가 불명확할 경우, 시세 API 호출 시간으로 동기화한다.
        payload = {"stk_cd": "005930_AL"}
        await self.client.post("/api/dostk/stkinfo", api_id="ka10001", payload=payload, is_order=False)
        return datetime.now(timezone.utc)
