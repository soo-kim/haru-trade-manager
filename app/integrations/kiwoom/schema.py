from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def first_non_empty(data: dict[str, Any], keys: list[str], *, deep: bool = True) -> Any | None:
    for key in keys:
        value = data.get(key)
        if _present(value):
            return value
    if not deep:
        return None
    for container_key in ("output", "output1", "output2", "data", "result"):
        nested = data.get(container_key)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if _present(value):
                    return value
    return None


def first_list(data: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    for key in keys:
        raw = data.get(key)
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
    for container_key in ("output", "output1", "output2", "data", "result"):
        nested = data.get(container_key)
        if isinstance(nested, dict):
            for key in keys:
                raw = nested.get(key)
                if isinstance(raw, list):
                    return [x for x in raw if isinstance(x, dict)]
    return []


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.replace(",", "").strip()
        if text == "":
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def parse_price(value: Any) -> float | None:
    parsed = parse_float(value)
    if parsed is None:
        return None
    return abs(parsed)


def parse_dt_any(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        try:
            dt = datetime.fromisoformat(stripped)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass

        digits = "".join(ch for ch in stripped if ch.isdigit())
        if len(digits) in {8, 12, 14}:
            padded = digits.ljust(14, "0")
            try:
                return datetime.strptime(padded[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                return None
    return None


def build_datetime(date_part: Any, time_part: Any) -> datetime | None:
    if date_part is None and time_part is None:
        return None
    if date_part is None:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    if time_part is None:
        time_part = "000000"
    text = f"{date_part}{time_part}"
    digits = "".join(ch for ch in str(text) if ch.isdigit()).ljust(14, "0")
    try:
        return datetime.strptime(digits[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    return True
