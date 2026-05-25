from datetime import datetime, timedelta, timezone

from app.repositories.paper import PaperRepository
from app.services.strategy_performance import StrategyPerformanceService
from tests.utils import build_session_factory


def test_strategy_performance_service_groups_by_strategy():
    maker = build_session_factory()
    repo = PaperRepository()
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    with maker() as db:
        repo.create_trade(
            db,
            ticker="005930",
            strategy_id="s1",
            side="buy",
            entry_price=100,
            exit_price=110,
            quantity=1,
            pnl=10,
            created_at=base,
        )
        repo.create_trade(
            db,
            ticker="005930",
            strategy_id="s1",
            side="buy",
            entry_price=100,
            exit_price=95,
            quantity=1,
            pnl=-5,
            created_at=base + timedelta(minutes=5),
        )
        repo.create_trade(
            db,
            ticker="000660",
            strategy_id="s2",
            side="buy",
            entry_price=100,
            exit_price=120,
            quantity=1,
            pnl=20,
            created_at=base + timedelta(minutes=10),
        )

    service = StrategyPerformanceService(session_factory=maker)
    report = service.report()
    assert report["ok"] is True
    assert report["meta"]["total"] == 2
    top = report["items"][0]
    assert top["strategy_id"] in {"s1", "s2"}
    assert "win_rate" in top
    assert "payoff_ratio" in top


def test_strategy_performance_service_supports_filter_and_sort():
    maker = build_session_factory()
    repo = PaperRepository()
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    with maker() as db:
        repo.create_trade(
            db,
            ticker="005930",
            strategy_id="alpha",
            side="buy",
            entry_price=100,
            exit_price=120,
            quantity=1,
            pnl=20,
            created_at=base,
        )
        repo.create_trade(
            db,
            ticker="000660",
            strategy_id="beta",
            side="buy",
            entry_price=100,
            exit_price=90,
            quantity=1,
            pnl=-10,
            created_at=base + timedelta(minutes=5),
        )

    service = StrategyPerformanceService(session_factory=maker)
    report = service.report(strategy_query="alp", sort_by="strategy_id", sort_order="asc")
    assert report["ok"] is True
    assert report["meta"]["total"] == 1
    assert report["items"][0]["strategy_id"] == "alpha"
