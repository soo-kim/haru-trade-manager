from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.models.paper import PaperPortfolio, PaperTrade
from app.db.models.position import Position
from app.orders.broker import Broker


@dataclass(frozen=True)
class ExitDecision:
    should_exit: bool
    reason: str | None
    qty: float


class PositionManager:
    def __init__(self, broker: Broker, trail_atr_mult: float) -> None:
        self.broker = broker
        self.trail_atr_mult = trail_atr_mult

    def _decide_exit(self, position: Position, current_price: float, atr_value: float) -> ExitDecision:
        if position.state == "OPEN":
            if current_price <= position.stop_price:
                return ExitDecision(True, "stop_loss", position.remaining_quantity)
            if current_price >= position.take_profit_price:
                half_qty = max(position.remaining_quantity / 2.0, 0.0)
                return ExitDecision(True, "take_profit_half", half_qty)
            return ExitDecision(False, None, 0.0)

        if position.state == "HALF_CLOSED":
            highest = position.highest_price or current_price
            highest = max(highest, current_price)
            trailing = highest - (atr_value * self.trail_atr_mult)
            if current_price <= trailing:
                return ExitDecision(True, "trailing_stop", position.remaining_quantity)
            return ExitDecision(False, None, 0.0)

        return ExitDecision(False, None, 0.0)

    async def monitor_and_close(
        self,
        db: Session,
        position: Position,
        current_price: float,
        atr_value: float,
    ) -> bool:
        decision = self._decide_exit(position, current_price, atr_value)
        if not decision.should_exit:
            if position.state == "HALF_CLOSED":
                highest = position.highest_price or current_price
                position.highest_price = max(highest, current_price)
                position.trailing_stop_price = position.highest_price - (atr_value * self.trail_atr_mult)
                db.commit()
            return False

        fill = await self.broker.place_exit_market(position.ticker, decision.qty)
        if not fill.ok:
            return False

        if decision.reason == "take_profit_half":
            position.state = "HALF_CLOSED"
            position.remaining_quantity -= decision.qty
            position.highest_price = current_price
            position.trailing_stop_price = current_price - (atr_value * self.trail_atr_mult)
            db.commit()
            return True

        position.remaining_quantity = max(position.remaining_quantity - decision.qty, 0.0)
        if position.remaining_quantity <= 0:
            position.state = "CLOSED"
            position.closed_time = datetime.now()
            position.close_reason = decision.reason
        db.commit()
        return True

    async def force_close(self, db: Session, position: Position, reason: str) -> bool:
        if position.state == "CLOSED" or position.remaining_quantity <= 0:
            return False
        fill = await self.broker.place_exit_market(position.ticker, position.remaining_quantity)
        if not fill.ok:
            return False
        closing_qty = position.remaining_quantity
        position.remaining_quantity = 0.0
        position.state = "CLOSED"
        position.closed_time = datetime.now()
        position.close_reason = reason
        if settings.trading_mode == "paper":
            trade = db.query(PaperTrade).filter(PaperTrade.ticker == position.ticker, PaperTrade.exit_price.is_(None)).first()
            if trade is not None:
                trade.exit_price = position.entry_price
                trade.pnl = 0.0
            pf = db.query(PaperPortfolio).filter(PaperPortfolio.ticker == position.ticker).first()
            if pf is not None:
                pf.quantity = max(pf.quantity - closing_qty, 0.0)
        db.commit()
        return True
