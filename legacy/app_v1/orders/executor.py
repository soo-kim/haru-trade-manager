import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.models.order import Order
from app.db.models.paper import PaperOrder, PaperPortfolio, PaperTrade
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.orders.broker import Broker
from app.risk.engine import RiskEngine
from app.runtime.signal_queue import SignalEvent

logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, broker: Broker, risk_engine: RiskEngine, notifier: object | None = None) -> None:
        self.broker = broker
        self.risk_engine = risk_engine
        self.notifier = notifier

    async def execute_signal(self, db: Session, event: SignalEvent) -> None:
        signal = Signal(
            ticker=event.ticker,
            strategy_id=event.strategy_id,
            timeframe=event.timeframe,
            signal_type=event.signal_type,
            side=event.side,
            signal_price=event.price,
            signal_time=event.signal_time,
            status="accepted",
        )
        db.add(signal)
        db.flush()

        fill = await self.broker.place_entry(event.ticker, qty=1.0, price=event.price)
        order_status = "filled" if fill.ok else "rejected"
        order = Order(
            position_id=None,
            external_order_id=fill.order_id,
            ticker=event.ticker,
            strategy_id=event.strategy_id,
            side=event.side,
            order_type="limit",
            price=event.price,
            quantity=1.0,
            filled_quantity=fill.filled_qty,
            status=order_status,
            reason=fill.error or "signal_entry",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(order)
        db.flush()

        if fill.ok:
            atr_value = self.risk_engine.compute_atr_value(db, event.ticker, event.timeframe, fallback_price=event.price)
            stop_price = max(event.price - (atr_value * self.risk_engine.stop_atr_mult()), 0.0)
            tp_price = event.price + (atr_value * self.risk_engine.tp_atr_mult())
            position = Position(
                ticker=event.ticker,
                strategy_id=event.strategy_id,
                state="OPEN",
                entry_price=event.price,
                stop_price=stop_price,
                take_profit_price=tp_price,
                trailing_stop_price=None,
                highest_price=event.price,
                quantity=fill.filled_qty,
                remaining_quantity=fill.filled_qty,
                entry_time=datetime.now(),
                closed_time=None,
                close_reason=None,
            )
            db.add(position)
            db.flush()
            order.position_id = position.id

            if settings.trading_mode == "paper":
                db.add(
                    PaperOrder(
                        ticker=event.ticker,
                        side=event.side,
                        order_type="limit",
                        price=event.price,
                        quantity=fill.filled_qty,
                        status="filled",
                    )
                )
                db.add(
                    PaperTrade(
                        ticker=event.ticker,
                        side=event.side,
                        entry_price=event.price,
                        exit_price=None,
                        quantity=fill.filled_qty,
                        pnl=None,
                    )
                )
                portfolio = db.query(PaperPortfolio).filter(PaperPortfolio.ticker == event.ticker).first()
                if portfolio is None:
                    portfolio = PaperPortfolio(ticker=event.ticker, quantity=fill.filled_qty, avg_price=event.price)
                    db.add(portfolio)
                else:
                    new_qty = portfolio.quantity + fill.filled_qty
                    if new_qty > 0:
                        portfolio.avg_price = (
                            (portfolio.avg_price * portfolio.quantity) + (event.price * fill.filled_qty)
                        ) / new_qty
                    portfolio.quantity = new_qty

        db.commit()
        if self.notifier and fill.ok:
            try:
                await self.notifier.send_message(
                    f"[ENTRY] {event.ticker} strategy={event.strategy_id} price={event.price} qty={fill.filled_qty}"
                )
            except Exception:  # noqa: BLE001
                pass

        logger.info(
            "signal accepted and order queued",
            extra={"event": "signal_to_order"},
        )
