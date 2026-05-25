from datetime import datetime, timedelta, timezone

from app.repositories.paper import PaperRepository
from app.services.paper_report import PaperReportService
from tests.utils import build_session_factory


def test_paper_report_passes_when_all_prd_thresholds_are_met():
    maker = build_session_factory()
    repo = PaperRepository()
    base = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    with maker() as db:
        for i in range(100):
            day = base + timedelta(days=i % 20)
            pnl = 10_000 if i < 60 else -6_000
            repo.create_trade(
                db,
                ticker="005930",
                side="buy",
                entry_price=100_000,
                exit_price=100_100,
                quantity=1,
                pnl=pnl,
                created_at=day,
            )

    service = PaperReportService(
        session_factory=maker,
        runtime_health_provider=lambda: {"cycle_count": 10_000, "error_count": 5},
    )
    report = service.build_report()

    assert report["ok"] is True
    assert report["passed"] is True
    assert report["metrics"]["total_signals"] == 100
    assert report["metrics"]["operating_days"] >= 14


def test_paper_report_fails_when_core_criteria_not_met():
    maker = build_session_factory()
    repo = PaperRepository()
    t0 = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)

    with maker() as db:
        for i in range(20):
            repo.create_trade(
                db,
                ticker="000660",
                side="buy",
                entry_price=100_000,
                exit_price=99_000,
                quantity=1,
                pnl=-1_000,
                created_at=t0 + timedelta(days=i % 3),
            )

    service = PaperReportService(
        session_factory=maker,
        runtime_health_provider=lambda: {"cycle_count": 100, "error_count": 1},
    )
    report = service.build_report()

    assert report["ok"] is True
    assert report["passed"] is False
    assert report["metrics"]["total_signals"] == 20
