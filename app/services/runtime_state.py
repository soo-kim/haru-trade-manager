from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class PendingConfigChange:
    key: str
    value: str
    changed_by: str = "telegram"


@dataclass
class RuntimeState:
    entry_paused: bool = False
    all_paused: bool = False
    halted: bool = False
    halt_reason: str | None = None
    halted_at: datetime | None = None
    pending_change: PendingConfigChange | None = None

    def pause_entry(self) -> None:
        self.entry_paused = True
        self.all_paused = False

    def pause_all(self) -> None:
        self.entry_paused = True
        self.all_paused = True

    def halt(self, reason: str) -> None:
        self.pause_all()
        self.halted = True
        self.halt_reason = reason
        self.halted_at = datetime.now(timezone.utc)

    def resume(self) -> None:
        self.entry_paused = False
        self.all_paused = False
        self.halted = False
        self.halt_reason = None
