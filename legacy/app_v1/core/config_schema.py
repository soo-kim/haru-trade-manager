from dataclasses import dataclass


@dataclass(frozen=True)
class RangeRule:
    key: str
    min_value: float
    max_value: float
    value_type: type


RANGE_RULES: dict[str, RangeRule] = {
    "position_size_max_pct": RangeRule("position_size_max_pct", 1.0, 30.0, float),
    "position_size_min_pct": RangeRule("position_size_min_pct", 0.5, 10.0, float),
    "risk_per_trade_pct": RangeRule("risk_per_trade_pct", 0.1, 3.0, float),
    "daily_loss_pct": RangeRule("daily_loss_pct", 0.5, 10.0, float),
    "max_positions": RangeRule("max_positions", 1, 30, int),
    "order_cancel_minutes": RangeRule("order_cancel_minutes", 1, 30, int),
    "liquidity_threshold": RangeRule("liquidity_threshold", 10.0, 500.0, float),
    "slippage_pct": RangeRule("slippage_pct", 0.0, 0.5, float),
    "margin_ratio": RangeRule("margin_ratio", 1.0, 2.5, float),
}


DEFAULT_CONFIGS: dict[str, str] = {
    "position_size_max_pct": "10",
    "position_size_min_pct": "2",
    "risk_per_trade_pct": "0.5",
    "daily_loss_pct": "2",
    "max_positions": "10",
    "order_cancel_minutes": "3",
    "liquidity_threshold": "50",
    "slippage_pct": "0.05",
    "margin_ratio": "1.5",
    "nxt_ratio": "50",
    "daily_base_capital": "10000000",
    "atr_period": "14",
    "stop_atr_mult": "1.5",
    "tp_atr_mult": "2.0",
    "trail_atr_mult": "1.5",
    "margin_close_time": "15:20",
    "margin_close_priority": "1,2,3,5,4",
    "sync_mode": "auto",
    "log_level": "INFO",
}


def validate_config_value(key: str, value: str) -> None:
    if key in RANGE_RULES:
        rule = RANGE_RULES[key]
        if rule.value_type is int:
            casted = int(value)
        else:
            casted = float(value)
        if casted < rule.min_value or casted > rule.max_value:
            raise ValueError(
                f"{key} must be between {rule.min_value} and {rule.max_value}"
            )

    if key == "sync_mode" and value not in {"auto", "manual"}:
        raise ValueError("sync_mode must be one of: auto, manual")

    if key == "log_level" and value not in {"DEBUG", "INFO"}:
        raise ValueError("log_level must be one of: DEBUG, INFO")

    if key == "margin_close_time":
        try:
            hh, mm = value.split(":")
            valid = 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59
        except Exception as exc:  # noqa: BLE001
            raise ValueError("margin_close_time must be HH:MM") from exc
        if not valid:
            raise ValueError("margin_close_time must be HH:MM")
