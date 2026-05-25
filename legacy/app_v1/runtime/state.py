from dataclasses import dataclass


@dataclass
class RuntimeState:
    paused_entry: bool = False
    paused_all: bool = False
    stop_requested: bool = False
    last_margin_close_date: str | None = None
    server_time_offset_sec: float = 0.0
