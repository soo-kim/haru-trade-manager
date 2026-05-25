import pytest

from app.core.config import ConfigManager


def test_read_only_key_blocked_without_override():
    cfg = ConfigManager(initial={"daily_base_capital": "10000000"})
    with pytest.raises(ValueError):
        cfg.set("daily_base_capital", "20000000")


def test_range_validation_and_success_set():
    cfg = ConfigManager(initial={"max_positions": "10", "margin_close_time": "15:20"})
    cfg.set("max_positions", "12")
    assert cfg.get("max_positions") == "12"
    with pytest.raises(ValueError):
        cfg.set("max_positions", "99")


def test_margin_close_time_format():
    cfg = ConfigManager(initial={"margin_close_time": "15:20"})
    with pytest.raises(ValueError):
        cfg.set("margin_close_time", "99:00")


def test_liquidity_threshold_allows_values_above_500():
    cfg = ConfigManager()
    cfg.set("liquidity_threshold", "800")
    assert cfg.get("liquidity_threshold") == "800"
    with pytest.raises(ValueError):
        cfg.set("liquidity_threshold", "9")


def test_removed_legacy_keys_rejected():
    cfg = ConfigManager()
    with pytest.raises(KeyError):
        cfg.set("bootstrap_enabled", "false")
    with pytest.raises(KeyError):
        cfg.set("server_time_offset_seconds", "0")
