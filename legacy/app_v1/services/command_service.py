from __future__ import annotations

from fastapi import HTTPException

from app.runtime.runner import RuntimeRunner


class CommandService:
    def __init__(self, runtime: RuntimeRunner | None) -> None:
        self.runtime = runtime

    def execute(self, command: str) -> str:
        if self.runtime is None:
            raise HTTPException(status_code=400, detail="runtime is disabled")

        cmd = command.strip().lower()
        if cmd in {"/pause", "/pause entry"}:
            self.runtime.state.paused_entry = True
            return "entry paused"
        if cmd == "/pause all":
            self.runtime.state.paused_all = True
            return "all paused"
        if cmd == "/resume":
            self.runtime.state.paused_all = False
            self.runtime.state.paused_entry = False
            return "resumed"
        if cmd == "/status":
            return (
                f"paused_entry={self.runtime.state.paused_entry}, "
                f"paused_all={self.runtime.state.paused_all}, "
                f"stop_requested={self.runtime.state.stop_requested}"
            )
        raise HTTPException(status_code=400, detail="unsupported command")
