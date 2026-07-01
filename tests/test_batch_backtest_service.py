from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.db.models.backtest import BacktestRun, BacktestTrade
from app.domain.models import Candle, Signal
from app.repositories.backtest import BacktestRepository
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository
from app.repositories.universe import UniverseRepository
from app.services.backtest_jobs import BacktestJobService
from app.services.batch_backtest import BatchBacktestRequest, BatchBacktestService
from tests.utils import build_session_factory


class AlwaysBuyStrategy:
    strategy_id = "always_buy"

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if len(candles) == 2:
            return Signal(index=1, side="buy", ticker=ticker, strategy_id=self.strategy_id, timeframe="3m", signal_time=now)
        return None


class NoSignalStrategy:
    strategy_id = "no_signal"

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        return None


class FailsForTickerStrategy:
    strategy_id = "partial_failure"

    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        if ticker == "000660":
            raise RuntimeError("strategy boom")
        if len(candles) == 2:
            return Signal(index=1, side="buy", ticker=ticker, strategy_id=self.strategy_id, timeframe="3m", signal_time=now)
        return None


def _candles(base: datetime, count: int, *, start_price: float = 100.0) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for idx in range(count):
        price = start_price + idx
        out.append(
            {
                "candle_time": base + timedelta(minutes=3 * idx),
                "open": price,
                "high": price + 3,
                "low": price - 1,
                "close": price + 2,
                "volume": 1000 + idx,
            }
        )
    return out


def test_backtest_repository_persists_parent_child_run_metadata() -> None:
    session_factory = build_session_factory()
    repo = BacktestRepository()
    now = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc)

    with session_factory() as db:
        parent = repo.create_run(
            db,
            run_id="batch-1",
            name="배치",
            strategy_id="always_buy",
            timeframe="3m",
            start_at=now,
            end_at=now + timedelta(days=1),
            params={},
            slippage_pct=0.05,
            commission_pct=0.0,
            status="queued",
            meta={"source": "batch"},
            created_at=now,
            run_type="batch_parent",
        )
        child = repo.create_run(
            db,
            run_id="child-1",
            name="005930",
            strategy_id="always_buy",
            timeframe="3m",
            start_at=now,
            end_at=now + timedelta(days=1),
            params={},
            slippage_pct=0.05,
            commission_pct=0.0,
            status="queued",
            meta={"source": "batch_child"},
            created_at=now,
            run_type="batch_child",
            parent_run_id=parent.id,
            ticker="005930",
        )
        children = repo.list_child_runs(db, parent_run_id="batch-1")
        parent_run_type = parent.run_type
        child_parent_run_id = child.parent_run_id
        child_ticker = child.ticker
        child_ids = [x.id for x in children]

    assert parent_run_type == "batch_parent"
    assert child_parent_run_id == "batch-1"
    assert child_ticker == "005930"
    assert child_ids == ["child-1"]


def test_batch_backtest_records_parent_children_exclusions_and_zero_signal_runs() -> None:
    async def scenario() -> tuple[str, dict[str, object]]:
        session_factory = build_session_factory()
        base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        universe_repo = UniverseRepository()
        candle_repo = CandleRepository()
        state_repo = CandleCollectionStateRepository()
        with session_factory() as db:
            universe_repo.upsert_symbol(db, ticker="005930", name="삼성전자", market="KOSPI", in_universe=True, is_active=True)
            universe_repo.upsert_symbol(db, ticker="000660", name="SK하이닉스", market="KOSPI", in_universe=True, is_active=True)
            universe_repo.upsert_symbol(db, ticker="035420", name="NAVER", market="KOSPI", in_universe=True, is_active=True)
            candle_repo.upsert_batch(db, ticker="005930", timeframe="3m", candles=_candles(base, 5))
            candle_repo.upsert_batch(db, ticker="000660", timeframe="3m", candles=_candles(base, 1))
            candle_repo.upsert_batch(db, ticker="035420", timeframe="3m", candles=_candles(base, 5))
            state_repo.record_success(
                db,
                ticker="005930",
                timeframe="3m",
                first_candle_time=base,
                last_candle_time=base + timedelta(minutes=12),
                row_count=5,
                source="test",
                collected_at=base + timedelta(minutes=15),
            )
            state_repo.record_success(
                db,
                ticker="000660",
                timeframe="3m",
                first_candle_time=base,
                last_candle_time=base,
                row_count=1,
                source="test",
                collected_at=base + timedelta(minutes=15),
            )
            state_repo.record_success(
                db,
                ticker="035420",
                timeframe="3m",
                first_candle_time=base,
                last_candle_time=base + timedelta(minutes=12),
                row_count=5,
                source="test",
                collected_at=base + timedelta(minutes=15),
            )

        def strategy_factory(strategy_id: str, timeframe: str, params: dict[str, object]):
            if strategy_id == "no_signal":
                return NoSignalStrategy()
            return AlwaysBuyStrategy()

        service = BatchBacktestService(
            session_factory=session_factory,
            universe_repo=universe_repo,
            candle_repo=candle_repo,
            state_repo=state_repo,
            backtest_repo=BacktestRepository(),
            strategy_factory=strategy_factory,
            now_fn=lambda: base + timedelta(hours=1),
        )
        batch_id = await service.run_batch(
            BatchBacktestRequest(
                strategy_id="always_buy",
                timeframe="3m",
                start=base,
                end=base + timedelta(minutes=12),
                min_candles=2,
                params={"slippage_pct": 0.0},
            )
        )
        status = await service.get_batch(batch_id)
        return batch_id, status or {}

    batch_id, status = asyncio.run(scenario())
    assert status["status"] == "completed"
    result = status["result"]
    assert result["run_type"] == "batch_parent"
    assert result["target_count"] == 3
    assert result["completed_count"] == 2
    assert result["excluded_count"] == 1
    assert result["exclude_reasons"] == {"insufficient_candles": 1}
    assert result["no_signal_count"] == 0
    assert result["trade_count"] >= 1

    session_factory = status["_test_session_factory"] if "_test_session_factory" in status else None
    assert batch_id


def test_batch_backtest_no_signals_is_completed_child_not_failure() -> None:
    async def scenario() -> dict[str, object]:
        session_factory = build_session_factory()
        base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        universe_repo = UniverseRepository()
        candle_repo = CandleRepository()
        state_repo = CandleCollectionStateRepository()
        backtest_repo = BacktestRepository()
        with session_factory() as db:
            universe_repo.upsert_symbol(db, ticker="005930", name="삼성전자", market="KOSPI", in_universe=True, is_active=True)
            candle_repo.upsert_batch(db, ticker="005930", timeframe="3m", candles=_candles(base, 5))
            state_repo.record_success(
                db,
                ticker="005930",
                timeframe="3m",
                first_candle_time=base,
                last_candle_time=base + timedelta(minutes=12),
                row_count=5,
                source="test",
                collected_at=base + timedelta(minutes=15),
            )
        service = BatchBacktestService(
            session_factory=session_factory,
            universe_repo=universe_repo,
            candle_repo=candle_repo,
            state_repo=state_repo,
            backtest_repo=backtest_repo,
            strategy_factory=lambda strategy_id, timeframe, params: NoSignalStrategy(),
            now_fn=lambda: base + timedelta(hours=1),
        )
        batch_id = await service.run_batch(
            BatchBacktestRequest(
                strategy_id="no_signal",
                timeframe="3m",
                start=base,
                end=base + timedelta(minutes=12),
                min_candles=2,
            )
        )
        with session_factory() as db:
            children = backtest_repo.list_child_runs(db, parent_run_id=batch_id)
            trades = db.query(BacktestTrade).all()
        status = await service.get_batch(batch_id)
        return {"children": children, "trades": trades, "status": status}

    result = asyncio.run(scenario())
    children = result["children"]
    assert len(children) == 1
    assert children[0].status == "completed"
    assert children[0].summary_json["trade_count"] == 0
    assert result["trades"] == []
    assert result["status"]["result"]["no_signal_count"] == 1


def test_batch_backtest_excludes_insufficient_candles_even_without_collection_state() -> None:
    async def scenario() -> dict[str, object]:
        session_factory = build_session_factory()
        base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        universe_repo = UniverseRepository()
        candle_repo = CandleRepository()
        backtest_repo = BacktestRepository()
        with session_factory() as db:
            universe_repo.upsert_symbol(db, ticker="005930", name="삼성전자", market="KOSPI", in_universe=True, is_active=True)
            candle_repo.upsert_batch(db, ticker="005930", timeframe="3m", candles=[])
        service = BatchBacktestService(
            session_factory=session_factory,
            universe_repo=universe_repo,
            candle_repo=candle_repo,
            state_repo=CandleCollectionStateRepository(),
            backtest_repo=backtest_repo,
            strategy_factory=lambda strategy_id, timeframe, params: AlwaysBuyStrategy(),
            now_fn=lambda: base + timedelta(hours=1),
        )
        batch_id = await service.run_batch(
            BatchBacktestRequest(
                strategy_id="always_buy",
                timeframe="3m",
                start=base,
                end=base + timedelta(minutes=12),
                min_candles=2,
            )
        )
        status = await service.get_batch(batch_id)
        children = await service.list_batch_items(batch_id)
        return {"status": status, "children": children}

    result = asyncio.run(scenario())
    assert result["status"]["status"] == "completed"
    assert result["status"]["result"]["completed_count"] == 0
    assert result["status"]["result"]["excluded_count"] == 1
    assert result["status"]["result"]["exclude_reasons"] == {"insufficient_candles": 1}
    assert result["children"][0]["status"] == "excluded"
    assert result["children"][0]["result"]["exclude_reason"] == "insufficient_candles"


def test_batch_persistent_job_dict_keeps_summary_for_completed_with_errors() -> None:
    session_factory = build_session_factory()
    repo = BacktestRepository()
    now = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc)
    with session_factory() as db:
        repo.create_run(
            db,
            run_id="batch-errors",
            name="배치 오류 포함",
            strategy_id="always_buy",
            timeframe="3m",
            start_at=now,
            end_at=now + timedelta(days=1),
            params={},
            slippage_pct=0.0,
            commission_pct=0.0,
            status="running",
            meta={"source": "batch_backtest", "run_type": "batch_parent"},
            created_at=now,
            run_type="batch_parent",
        )
        repo.mark_completed(
            db,
            run_id="batch-errors",
            summary={"run_type": "batch_parent", "failed_count": 1, "completed_count": 1},
            completed_at=now + timedelta(minutes=1),
            trades=[],
            equity_points=[],
            status="completed_with_errors",
        )
    service = BacktestJobService(session_factory=session_factory, backtest_repo=repo)

    job = asyncio.run(service.get_job("batch-errors"))

    assert job is not None
    assert job["status"] == "completed_with_errors"
    assert job["progress"] == 100
    assert job["result"] == {"run_type": "batch_parent", "failed_count": 1, "completed_count": 1}


def test_batch_backtest_keeps_running_when_one_child_fails() -> None:
    async def scenario() -> dict[str, object]:
        session_factory = build_session_factory()
        base = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        universe_repo = UniverseRepository()
        candle_repo = CandleRepository()
        state_repo = CandleCollectionStateRepository()
        backtest_repo = BacktestRepository()
        with session_factory() as db:
            for ticker in ["005930", "000660"]:
                universe_repo.upsert_symbol(db, ticker=ticker, name=ticker, market="KOSPI", in_universe=True, is_active=True)
                candle_repo.upsert_batch(db, ticker=ticker, timeframe="3m", candles=_candles(base, 5))
                state_repo.record_success(
                    db,
                    ticker=ticker,
                    timeframe="3m",
                    first_candle_time=base,
                    last_candle_time=base + timedelta(minutes=12),
                    row_count=5,
                    source="test",
                    collected_at=base + timedelta(minutes=15),
                )
        service = BatchBacktestService(
            session_factory=session_factory,
            universe_repo=universe_repo,
            candle_repo=candle_repo,
            state_repo=state_repo,
            backtest_repo=backtest_repo,
            strategy_factory=lambda strategy_id, timeframe, params: FailsForTickerStrategy(),
            now_fn=lambda: base + timedelta(hours=1),
        )
        batch_id = await service.run_batch(
            BatchBacktestRequest(
                strategy_id="partial_failure",
                timeframe="3m",
                start=base,
                end=base + timedelta(minutes=12),
                min_candles=2,
                params={"slippage_pct": 0.0},
            )
        )
        status = await service.get_batch(batch_id)
        children = await service.list_batch_items(batch_id)
        return {"status": status, "children": children}

    result = asyncio.run(scenario())
    status = result["status"]
    assert status["status"] == "completed_with_errors"
    assert status["result"]["completed_count"] == 1
    assert status["result"]["failed_count"] == 1
    children_by_ticker = {x["ticker"]: x for x in result["children"]}
    assert children_by_ticker["005930"]["status"] == "completed"
    assert children_by_ticker["000660"]["status"] == "failed"
    assert "strategy boom" in children_by_ticker["000660"]["error"]
