from datetime import datetime, timezone

from app.repositories.performance import PerformanceRepository
from tests.utils import build_session


def test_performance_repository_snapshot_and_cash_flow_roundtrip():
    repo = PerformanceRepository()
    with build_session() as db:
        snap = repo.create_snapshot(
            db,
            snapshot_time=datetime(2026, 1, 1, 7, 50, tzinfo=timezone.utc),
            snapshot_type="pre_market",
            total_assets=10_000_000,
            cash=6_000_000,
            stock_value=4_000_000,
        )
        flow = repo.create_cash_flow(
            db,
            flow_time=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
            amount=500_000,
            total_before=10_500_000,
            total_after=11_000_000,
            detected_by="manual",
        )

        snapshots = repo.list_snapshots(db)
        flows = repo.list_cash_flows(db)

    assert snap.id > 0
    assert flow.id > 0
    assert len(snapshots) == 1
    assert len(flows) == 1
    assert snapshots[0].snapshot_type == "pre_market"
    assert flows[0].detected_by == "manual"
