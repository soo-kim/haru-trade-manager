import asyncio
from datetime import date

from app.services.daily_report import DailyIncidentReporter
from app.services.runtime_safety import RuntimeSafetyManager
from app.services.runtime_state import RuntimeState


class FakeSink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, text: str) -> bool:
        self.messages.append(text)
        return True


def test_daily_report_build_and_send_once():
    runtime = RuntimeState()
    sink = FakeSink()
    safety = RuntimeSafetyManager(runtime=runtime)
    reporter = DailyIncidentReporter(safety=safety, alert_sink=sink)

    day = date.today()
    # 장애가 없는 경우
    text = reporter.build_report_text(day)
    assert "장애 건수: 0" in text

    # 장애를 추가한 경우
    asyncio.run(safety.critical(code="order_unresolved", message="a"))
    asyncio.run(safety.critical(code="order_unresolved", message="b"))
    asyncio.run(safety.critical(code="loop_cycle_failed", message="x"))

    report = reporter.build_report_text(day)
    assert "장애 건수:" in report
    assert "order_unresolved" in report
    assert "loop_cycle_failed" in report

    first = asyncio.run(reporter.send_report_once_per_day(day))
    second = asyncio.run(reporter.send_report_once_per_day(day))
    assert first is True
    assert second is False
    assert len(sink.messages) == 1


def test_weekly_report_build_and_send_once_per_week():
    runtime = RuntimeState()
    sink = FakeSink()
    safety = RuntimeSafetyManager(runtime=runtime)
    reporter = DailyIncidentReporter(safety=safety, alert_sink=sink)

    day = date.today()
    asyncio.run(safety.critical(code="order_unresolved", message="a"))
    text = reporter.build_weekly_report_text(day, days=7)
    assert "[주간 운영 리포트]" in text

    first = asyncio.run(reporter.send_weekly_report_once_per_week(day))
    second = asyncio.run(reporter.send_weekly_report_once_per_week(day))
    assert first is True
    assert second is False
    assert len(sink.messages) == 1


def test_daily_report_includes_auto_backtest_section_when_provider_exists():
    runtime = RuntimeState()
    reporter = DailyIncidentReporter(
        safety=RuntimeSafetyManager(runtime=runtime),
        backtest_status_provider=lambda: {
            "enabled": True,
            "last_status": "triggered",
            "last_job_id": "job-1",
            "last_job_snapshot": {
                "status": "completed",
                "result": {"trade_count": 12, "win_rate": 0.55, "total_pnl": 12345, "sharpe_ratio": 1.2, "mdd": 0.08},
            },
        },
    )
    text = reporter.build_report_text(date.today())
    assert "자동백테스트:" in text
    assert "자동백테스트결과:" in text


def test_daily_report_includes_strategy_top_bottom_summary():
    runtime = RuntimeState()
    reporter = DailyIncidentReporter(
        safety=RuntimeSafetyManager(runtime=runtime),
        strategy_summary_provider=lambda: {
            "ok": True,
            "items": [
                {"strategy_id": "top", "total_pnl": 100, "win_rate": 0.6, "expectancy": 3},
                {"strategy_id": "bottom", "total_pnl": -50, "win_rate": 0.3, "expectancy": -2},
            ],
        },
    )
    text = reporter.build_report_text(date.today())
    assert "상위전략:" in text
    assert "하위전략:" in text
