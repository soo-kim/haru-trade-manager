import asyncio

from app.services.runtime_safety import RuntimeSafetyManager
from app.services.runtime_state import RuntimeState


class FakeAlertSink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, text: str) -> bool:
        self.messages.append(text)
        return True


def test_runtime_safety_halts_and_sends_alert():
    runtime = RuntimeState()
    alert = FakeAlertSink()
    safety = RuntimeSafetyManager(runtime=runtime, alert_sink=alert)

    asyncio.run(safety.critical(code="order_status_check_failed", message="status api timeout"))

    assert runtime.halted is True
    assert runtime.all_paused is True
    assert runtime.entry_paused is True
    assert runtime.halt_reason is not None
    assert "order_status_check_failed" in runtime.halt_reason
    assert len(alert.messages) == 1
    events = safety.latest_events()
    assert len(events) == 1
    assert events[0].code == "order_status_check_failed"
