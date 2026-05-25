from datetime import datetime, timezone

from app.integrations.kiwoom.schema import build_datetime, first_list, first_non_empty, parse_dt_any, parse_float, parse_price


def test_first_non_empty_supports_nested_outputs():
    data = {"output": {"stck_prpr": "70100"}}
    assert first_non_empty(data, ["stck_prpr"]) == "70100"


def test_first_list_supports_output2():
    data = {"output2": {"rows": [{"a": 1}, {"a": 2}]}}
    rows = first_list(data, ["rows"])
    assert len(rows) == 2


def test_parse_float_and_datetime_helpers():
    assert parse_float("70,100") == 70100.0
    assert parse_float("") is None
    assert parse_price("-70,100") == 70100.0

    dt = parse_dt_any("2026-01-01T09:00:00+00:00")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None

    built = build_datetime("20260101", "090500")
    assert built == datetime(2026, 1, 1, 9, 5, tzinfo=timezone.utc)
