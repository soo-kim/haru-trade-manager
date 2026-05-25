from datetime import datetime, timedelta, timezone

from app.repositories.paper import PaperRepository
from app.services.performance import PerformanceService
from tests.utils import build_session_factory


def test_performance_service_detects_cash_flow_and_computes_twr():
    maker = build_session_factory()
    service = PerformanceService(session_factory=maker)
    paper_repo = PaperRepository()

    t0 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(days=1)
    t2 = t1 + timedelta(days=1)

    service.record_snapshot(
        snapshot_time=t0,
        snapshot_type="pre_market",
        total_assets=10_000_000,
        cash=10_000_000,
        stock_value=0,
    )
    with maker() as db:
        paper_repo.create_trade(
            db,
            ticker="005930",
            side="buy",
            entry_price=70_000,
            exit_price=73_500,
            quantity=100,
            pnl=500_000,
            created_at=t1,
        )

    service.record_snapshot(
        snapshot_time=t1,
        snapshot_type="market_close",
        total_assets=10_500_000,
        cash=10_500_000,
        stock_value=0,
    )

    with maker() as db:
        paper_repo.create_trade(
            db,
            ticker="000660",
            side="buy",
            entry_price=120_000,
            exit_price=126_000,
            quantity=100,
            pnl=500_000,
            created_at=t2,
        )

    service.record_snapshot(
        snapshot_time=t2,
        snapshot_type="after_close",
        total_assets=11_500_000,
        cash=11_500_000,
        stock_value=0,
    )

    detect = service.detect_cash_flows()
    assert detect["ok"] is True
    assert detect["created"] == 1
    assert abs(float(detect["items"][0]["amount"]) - 500_000) < 1e-6

    report = service.twr_report()
    assert report["ok"] is True
    assert abs(float(report["twr"]) - 0.1) < 1e-6
    assert abs(float(report["cumulative_pnl"]) - 1_000_000) < 1e-6
    assert abs(float(report["realized_trade_pnl"]) - 1_000_000) < 1e-6
    assert abs(float(report["account_drift"])) < 1e-6

    listed_snapshots = service.list_snapshot_records(limit=2, offset=1)
    assert listed_snapshots["ok"] is True
    assert len(listed_snapshots["items"]) == 2

    listed_flows = service.list_cash_flow_records(detected_by="auto")
    assert listed_flows["ok"] is True
    assert len(listed_flows["items"]) == 1
