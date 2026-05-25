from __future__ import annotations

from typing import Protocol

from app.domain.models import OrderRequest, OrderResult, OrderStatus


class OrderGateway(Protocol):
    async def place_order(self, req: OrderRequest) -> OrderResult:
        raise NotImplementedError

    async def get_order_status(self, order_id: str) -> OrderStatus:
        raise NotImplementedError


class CriticalSafety(Protocol):
    async def critical(self, *, code: str, message: str) -> None:
        raise NotImplementedError


class OrderService:
    """
    Non-negotiable rule:
    When order placement fails, we must check status before retry.
    """

    def __init__(self, gateway: OrderGateway, *, safety: CriticalSafety | None = None) -> None:
        self.gateway = gateway
        self.safety = safety

    async def place_with_reconcile(self, req: OrderRequest) -> OrderResult:
        try:
            first = await self.gateway.place_order(req)
        except Exception as exc:  # noqa: BLE001
            await self._critical("order_place_exception", f"{req.ticker} {req.side}: {exc}")
            first = OrderResult(ok=False, order_id=None, error=str(exc))
        if first.ok:
            return first

        if first.order_id:
            try:
                st = await self.gateway.get_order_status(first.order_id)
            except Exception as exc:  # noqa: BLE001
                await self._critical(
                    "order_status_check_failed",
                    f"{req.ticker} first order_id={first.order_id}: {exc}",
                )
                return OrderResult(ok=False, order_id=first.order_id, error="status_check_failed")
            if st.exists and st.status in {"accepted", "partial", "filled"}:
                return OrderResult(ok=True, order_id=first.order_id)

        try:
            second = await self.gateway.place_order(req)
        except Exception as exc:  # noqa: BLE001
            await self._critical("order_retry_exception", f"{req.ticker} {req.side}: {exc}")
            second = OrderResult(ok=False, order_id=None, error=str(exc))
        if second.ok:
            return second

        if second.order_id:
            try:
                st2 = await self.gateway.get_order_status(second.order_id)
            except Exception as exc:  # noqa: BLE001
                await self._critical(
                    "order_status_check_failed",
                    f"{req.ticker} second order_id={second.order_id}: {exc}",
                )
                return OrderResult(ok=False, order_id=second.order_id, error="status_check_failed")
            if st2.exists and st2.status in {"accepted", "partial", "filled"}:
                return OrderResult(ok=True, order_id=second.order_id)

        await self._critical(
            "order_unresolved",
            f"{req.ticker} {req.side} unresolved after reconcile",
        )
        return OrderResult(ok=False, order_id=second.order_id, error=second.error or first.error or "unresolved")

    async def _critical(self, code: str, message: str) -> None:
        if self.safety is None:
            return
        await self.safety.critical(code=code, message=message)
