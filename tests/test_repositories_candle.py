from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.candle import Candle
from app.repositories.candle import CandleRepository
from tests.utils import build_session


def test_candle_repository_incremental_upsert():
    repo = CandleRepository()
    t1 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)

    with build_session() as db:
        repo.upsert_incremental(
            db,
            ticker="005930",
            timeframe="5m",
            candle_time=t1,
            open_price=100,
            high=101,
            low=99,
            close=100,
            volume=1000,
        )
        repo.upsert_incremental(
            db,
            ticker="005930",
            timeframe="5m",
            candle_time=t1,
            open_price=100,
            high=102,
            low=98,
            close=101,
            volume=1200,
        )
        repo.upsert_incremental(
            db,
            ticker="005930",
            timeframe="5m",
            candle_time=t2,
            open_price=101,
            high=103,
            low=100,
            close=102,
            volume=1300,
        )

        rows = db.scalars(select(Candle).order_by(Candle.candle_time)).all()
        assert len(rows) == 2
        assert rows[0].high == 102
        assert rows[1].close == 102
