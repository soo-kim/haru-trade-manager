from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Protocol

from app.core.settings import settings
from app.services.runtime_state import RuntimeState


class AlertSink(Protocol):
    async def send_message(self, text: str) -> bool:
        raise NotImplementedError


@dataclass(frozen=True)
class RuntimeEvent:
    level: str
    code: str
    message: str
    created_at: datetime


class RuntimeSafetyManager:
    def __init__(self, *, runtime: RuntimeState, alert_sink: AlertSink | None = None, max_events: int = 200) -> None:
        self.runtime = runtime
        self.alert_sink = alert_sink
        self.max_events = max_events
        self._events: list[RuntimeEvent] = []

    async def critical(self, *, code: str, message: str) -> None:
        event = RuntimeEvent(level="CRITICAL", code=code, message=message, created_at=datetime.now(timezone.utc))
        self._events.append(event)
        if len(self._events) > self.max_events:
            self._events.pop(0)
        self.runtime.halt(f"{code}: {message}")
        if self.alert_sink is not None:
            await self.alert_sink.send_message(f"[치명 장애] {code}: {message}")

    def latest_events(self, limit: int = 20) -> list[RuntimeEvent]:
        if limit <= 0:
            return []
        return self._events[-limit:]

    def events_on(self, day: date) -> list[RuntimeEvent]:
        tz = _server_timezone()
        return [e for e in self._events if e.created_at.astimezone(tz).date() == day]


def _server_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.server_timezone)
    except Exception:  # noqa: BLE001
        return ZoneInfo("UTC")
