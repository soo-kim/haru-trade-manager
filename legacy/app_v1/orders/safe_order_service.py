from __future__ import annotations

import logging

from app.integrations.kiwoom.gateway import KiwoomGateway, OrderRequest, OrderResult

logger = logging.getLogger(__name__)


class SafeOrderService:
    def __init__(self, gateway: KiwoomGateway) -> None:
        self.gateway = gateway

    async def place_with_reconcile(self, request: OrderRequest) -> OrderResult:
        first = await self.gateway.place_order(request)
        if first.ok:
            return first

        # 주문 실패 시 무조건 상태 조회를 먼저 수행한다.
        if first.order_id:
            status = await self.gateway.get_order_status(first.order_id)
            if status.exists and status.status in {"filled", "partial", "accepted"}:
                logger.warning("first attempt recovered by status query", extra={"event": "order_recovered"})
                return OrderResult(ok=True, order_id=first.order_id)

        second = await self.gateway.place_order(request)
        if second.ok:
            return second

        if second.order_id:
            second_status = await self.gateway.get_order_status(second.order_id)
            if second_status.exists and second_status.status in {"filled", "partial", "accepted"}:
                return OrderResult(ok=True, order_id=second.order_id)

        return OrderResult(
            ok=False,
            order_id=second.order_id,
            error=second.error or first.error or "order_status_unresolved",
        )
