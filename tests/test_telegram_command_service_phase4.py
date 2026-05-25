from app.core.config import ConfigManager
from app.services.config_service import ConfigService
from app.services.runtime_state import RuntimeState
from app.services.telegram_command_service import TelegramCommandService


def test_set_risk_key_requires_confirm():
    manager = ConfigManager()
    service = TelegramCommandService(config=ConfigService(manager), runtime=RuntimeState())

    first = service.handle("/set max_positions 12")
    assert first.ok is True
    assert "/confirm 을 실행하세요." in first.message
    assert manager.get("max_positions") == "10"

    confirmed = service.handle("/confirm")
    assert confirmed.ok is True
    assert manager.get("max_positions") == "12"


def test_blocked_key_rejected_in_telegram():
    manager = ConfigManager()
    service = TelegramCommandService(config=ConfigService(manager), runtime=RuntimeState())
    result = service.handle("/set atr_period 20")
    assert result.ok is False
    assert "웹 UI에서만" in result.message


def test_pause_and_resume_commands():
    runtime = RuntimeState()
    service = TelegramCommandService(config=ConfigService(ConfigManager()), runtime=runtime)

    paused = service.handle("/pause all")
    assert paused.ok is True
    assert runtime.all_paused is True
    assert runtime.entry_paused is True

    resumed = service.handle("/resume")
    assert resumed.ok is True
    assert runtime.all_paused is False
    assert runtime.entry_paused is False


def test_status_command_includes_runtime_and_backtest_summary():
    runtime = RuntimeState()
    runtime.pause_entry()
    service = TelegramCommandService(
        config=ConfigService(ConfigManager()),
        runtime=runtime,
        runtime_status_provider=lambda: {"loop_running": True, "loop_cycles": 42, "loop_last_ms": 101.7},
        backtest_status_provider=lambda: {"last_status": "completed", "last_job_id": "job-9"},
    )
    result = service.handle("/status")
    assert result.ok is True
    assert "진입중지=True" in result.message
    assert "루프실행=True" in result.message
    assert "루프사이클=42" in result.message
    assert "자동백테스트상태=completed" in result.message


def test_paper_report_command_returns_summary():
    service = TelegramCommandService(
        config=ConfigService(ConfigManager()),
        runtime=RuntimeState(),
        paper_report_provider=lambda: {
            "ok": True,
            "passed": True,
            "metrics": {
                "total_signals": 100,
                "win_rate": 0.6,
                "sharpe_ratio": 1.5,
                "mdd": 0.1,
                "error_rate": 0.0001,
            },
        },
        backtest_status_provider=lambda: {"last_status": "completed", "last_job_id": "job-1"},
    )
    result = service.handle("/paper_report")
    assert result.ok is True
    assert "페이퍼합격여부=True" in result.message
    assert "자동백테스트상태=completed" in result.message
    assert "자동백테스트작업=job-1" in result.message


def test_report_command_includes_auto_backtest_summary():
    service = TelegramCommandService(
        config=ConfigService(ConfigManager()),
        runtime=RuntimeState(),
        report_provider=lambda: "일일 리포트 본문",
        backtest_status_provider=lambda: {"last_status": "triggered", "last_job_id": "job-77"},
    )
    result = service.handle("/report")
    assert result.ok is True
    assert "일일 리포트 본문" in result.message
    assert "자동백테스트상태=triggered" in result.message
    assert "자동백테스트작업=job-77" in result.message
