import asyncio
from datetime import datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config_manager import ConfigManager
from app.core.settings import settings
from app.db.base import Base
from app.db.models.candle import Candle
from app.db.models.order import Order
from app.db.models.universe import Symbol
from app.loops.loop_a import LoopA
from app.loops.loop_b import LoopB
from app.orders.broker import PaperBroker
from app.risk.engine import RiskEngine
from app.runtime.signal_queue import SignalQueue
from app.runtime.state import RuntimeState
from tests.utils import build_session, reset_manager
import app.loops.loop_a as loop_a_module
import app.loops.loop_b as loop_b_module
import app.db.models  # noqa: F401


def test_loop_b_to_loop_a_pipeline():
    manager = reset_manager()
    state = RuntimeState()
    queue = SignalQueue()
    risk_engine = RiskEngine(manager)
    loop_b = LoopB(queue=queue, state=state)

    with build_session() as db:
        manager.load(db)
    loop_a = LoopA(queue=queue, state=state, risk_engine=risk_engine, broker=PaperBroker())

    test_engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    Base.metadata.create_all(bind=test_engine)
    test_maker = sessionmaker(bind=test_engine, class_=Session, autocommit=False, autoflush=False)

    original_session_local = loop_a_module.SessionLocal
    original_loop_b_session_local = loop_b_module.SessionLocal
    loop_a_module.SessionLocal = test_maker
    loop_b_module.SessionLocal = test_maker
    try:
        with test_maker() as db:
            manager.load(db)
            db.add(Symbol(ticker="005930", name="Samsung", market="KOSPI", in_universe=True, is_active=True, is_blocked=False, status="normal"))
            db.add(Candle(ticker="005930", timeframe="5m", candle_time=datetime(2026, 1, 1, 9, 0, 0), open=100, high=101, low=99, close=100, volume=10000))
            db.add(Candle(ticker="005930", timeframe="5m", candle_time=datetime(2026, 1, 1, 9, 5, 0), open=103, high=104, low=102, close=103, volume=12000))
            db.commit()

        async def run_once():
            await loop_b.tick(datetime(2026, 1, 1, 9, 10, 0))
            await loop_a.tick()

        asyncio.run(run_once())

        with test_maker() as db:
            orders = db.scalars(select(Order)).all()
            assert len(orders) == 1
            assert orders[0].ticker == "005930"
    finally:
        loop_a_module.SessionLocal = original_session_local
        loop_b_module.SessionLocal = original_loop_b_session_local
