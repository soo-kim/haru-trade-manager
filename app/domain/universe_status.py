from __future__ import annotations

from enum import StrEnum


class UniverseStatus(StrEnum):
    NORMAL = "normal"
    EXIT_PENDING = "exit_pending"
    REMOVED = "removed"
    HALTED = "halted"


_STATUS_LABELS_KO: dict[UniverseStatus, str] = {
    UniverseStatus.NORMAL: "정상",
    UniverseStatus.EXIT_PENDING: "이탈 예정",
    UniverseStatus.REMOVED: "제외됨",
    UniverseStatus.HALTED: "거래정지",
}


def universe_status_label_ko(raw_status: str) -> str:
    try:
        status = UniverseStatus(raw_status)
    except ValueError:
        return f"알 수 없음({raw_status})"
    return _STATUS_LABELS_KO.get(status, f"알 수 없음({raw_status})")
