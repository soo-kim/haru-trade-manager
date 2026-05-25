from datetime import datetime, timezone

from sqlalchemy import select

from app.data.candle_sync import CandleSyncService
from app.db.models.candle import Candle
from tests.utils import build_session


def test_incremental_sync_updates_last_bar_and_inserts_new_bar():
    service = CandleSyncService()
    t1 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)

    with build_session() as db:
        service.upsert_incremental(db, "005930", "5m", t1, 100, 101, 99, 100, 1000)
        service.upsert_incremental(db, "005930", "5m", t1, 100, 102, 98, 101, 1500)
        service.upsert_incremental(db, "005930", "5m", t2, 101, 103, 100, 102, 1300)

        candles = db.scalars(
            select(Candle).where(Candle.ticker == "005930", Candle.timeframe == "5m").order_by(Candle.candle_time)
        ).all()
        assert len(candles) == 2
        assert candles[0].high == 102
        assert candles[0].close == 101
        assert candles[1].candle_time.replace(tzinfo=timezone.utc) == t2
