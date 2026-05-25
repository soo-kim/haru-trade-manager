from __future__ import annotations

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class Rule:
    min_value: float | None = None
    max_value: float | None = None
    read_only: bool = False
    as_int: bool = False
    allowed_values: tuple[str, ...] | None = None


class ConfigManager:
    """
    Rebuild config manager with explicit validation and read-only protection.
    All runtime modules are expected to receive this manager via DI.
    """

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._lock = RLock()
        self._rules: dict[str, Rule] = {
            "position_size_max_pct": Rule(min_value=1, max_value=30),
            "position_size_min_pct": Rule(min_value=0.5, max_value=10),
            "max_positions": Rule(min_value=1, max_value=30, as_int=True),
            "risk_per_trade_pct": Rule(min_value=0.1, max_value=3.0),
            "daily_loss_pct": Rule(min_value=0.5, max_value=10),
            "stop_count": Rule(min_value=1, max_value=20, as_int=True),
            "cooldown_hours": Rule(min_value=0, max_value=72, as_int=True),
            "order_cancel_minutes": Rule(min_value=1, max_value=30, as_int=True),
            "slippage_pct": Rule(min_value=0, max_value=0.5),
            "liquidity_threshold": Rule(min_value=10),
            "margin_ratio": Rule(min_value=1.0, max_value=2.5),
            "daily_base_capital": Rule(read_only=True),
            "margin_close_time": Rule(),
            "margin_close_priority": Rule(),
            "atr_period": Rule(min_value=5, max_value=30, as_int=True),
            "stop_atr_mult": Rule(min_value=0.5, max_value=5.0),
            "tp_atr_mult": Rule(min_value=0.5, max_value=10.0),
            "trail_atr_mult": Rule(min_value=0.5, max_value=5.0),
            "sync_mode": Rule(allowed_values=("auto", "manual")),
            "log_level": Rule(allowed_values=("DEBUG", "INFO")),
        }
        self._strategy_overridable_keys = {"stop_atr_mult", "tp_atr_mult", "trail_atr_mult"}
        self._display_meta: dict[str, tuple[str, str]] = {
            "position_size_max_pct": ("최대 포지션 비중(%)", "단일 종목 진입 시 허용되는 최대 자금 비중입니다."),
            "position_size_min_pct": ("최소 포지션 비중(%)", "단일 종목 진입 시 허용되는 최소 자금 비중입니다."),
            "max_positions": ("동시 보유 최대 개수", "동시에 열 수 있는 포지션의 최대 개수입니다."),
            "risk_per_trade_pct": ("거래당 리스크 비율(%)", "한 번의 거래에서 감수할 최대 손실 비율입니다."),
            "daily_loss_pct": ("일일 손실 한도(%)", "일일 손실이 이 비율을 넘으면 신규 진입을 제한합니다."),
            "stop_count": ("손절 허용 횟수", "일정 기간 내 손절 누적 허용 횟수입니다."),
            "cooldown_hours": ("쿨다운 시간(시간)", "손실 제한 이후 신규 진입을 멈추는 시간입니다."),
            "order_cancel_minutes": ("주문 취소 대기(분)", "미체결 주문을 취소하기 전 대기 시간입니다."),
            "slippage_pct": ("슬리피지(%)", "백테스트/주문 체결 시 반영할 슬리피지 비율입니다."),
            "liquidity_threshold": ("유동성 기준(억 원)", "유니버스 활성화 판단에 쓰는 일평균 거래대금 기준입니다. (최소 10, 상한 없음)"),
            "margin_ratio": ("증거금 비율", "증거금 기반 계산에 사용하는 비율 값입니다."),
            "daily_base_capital": ("기준 원금", "일간 손익/리스크 기준이 되는 읽기 전용 원금입니다."),
            "margin_close_time": ("마감 청산 시각", "장 마감 전 강제 청산 로직을 시작할 시각(HH:MM)입니다."),
            "margin_close_priority": ("마감 청산 우선순위", "전략 ID 기준 청산 우선순위를 쉼표로 지정합니다."),
            "atr_period": ("ATR 기간", "ATR 계산에 사용하는 봉 개수입니다."),
            "stop_atr_mult": ("손절 ATR 배수", "손절가 계산 시 ATR에 곱할 배수입니다."),
            "tp_atr_mult": ("익절 ATR 배수", "익절가 계산 시 ATR에 곱할 배수입니다."),
            "trail_atr_mult": ("트레일 ATR 배수", "트레일링 스탑 계산 시 ATR에 곱할 배수입니다."),
            "sync_mode": ("동기화 모드", "동기화 동작 방식을 auto/manual 중에서 지정합니다."),
            "log_level": ("로그 레벨", "애플리케이션 로그 출력 레벨입니다."),
        }
        self._values: dict[str, str] = {
            "position_size_max_pct": "10",
            "position_size_min_pct": "2",
            "max_positions": "10",
            "risk_per_trade_pct": "0.5",
            "daily_loss_pct": "2",
            "stop_count": "5",
            "cooldown_hours": "24",
            "order_cancel_minutes": "3",
            "slippage_pct": "0.05",
            "liquidity_threshold": "50",
            "margin_ratio": "1.5",
            "margin_close_time": "15:20",
            "margin_close_priority": "1,2,3,5,4",
            "atr_period": "14",
            "stop_atr_mult": "1.5",
            "tp_atr_mult": "2.0",
            "trail_atr_mult": "1.5",
            "sync_mode": "auto",
            "log_level": "INFO",
        }
        for key, value in dict(initial or {}).items():
            self.set(key, value, allow_read_only=True)

    def get(self, key: str) -> str:
        with self._lock:
            if key not in self._values:
                raise KeyError(f"unknown config key: {key}")
            return self._values[key]

    def get_all(self) -> dict[str, str]:
        with self._lock:
            return dict(self._values)

    def describe(self, key: str) -> dict[str, object]:
        with self._lock:
            if self._is_strategy_override_key(key):
                _, strategy_id, param = key.split(".", 2)
                base_label, base_desc = self._display_meta.get(
                    param,
                    (param, "전략별 override 설정값입니다."),
                )
                return {
                    "label": f"전략 {strategy_id} {base_label}",
                    "description": f"{base_desc} (전략 {strategy_id} 전용 override)",
                    "allowed_values": [],
                }

            label, desc = self._display_meta.get(
                key,
                (key, "설명이 등록되지 않은 설정 항목입니다."),
            )
            rule = self._rules.get(key)
            allowed_values = list(rule.allowed_values) if rule and rule.allowed_values is not None else []
            return {"label": label, "description": desc, "allowed_values": allowed_values}

    def set(self, key: str, value: str, *, allow_read_only: bool = False) -> None:
        with self._lock:
            rule = self._rules.get(key)
            if rule is None and not self._is_strategy_override_key(key):
                raise KeyError(f"unknown config key: {key}")
            if rule and rule.read_only and not allow_read_only:
                raise ValueError(f"{key} is read-only")

            if rule and (rule.min_value is not None or rule.max_value is not None):
                number = int(value) if rule.as_int else float(value)
                if rule.min_value is not None and number < rule.min_value:
                    raise ValueError(f"{key} must be >= {rule.min_value}")
                if rule.max_value is not None and number > rule.max_value:
                    raise ValueError(f"{key} must be <= {rule.max_value}")

            if rule and rule.allowed_values is not None and value not in rule.allowed_values:
                raise ValueError(f"{key} must be one of: {', '.join(rule.allowed_values)}")

            if key == "margin_close_time":
                parts = value.split(":")
                if len(parts) != 2:
                    raise ValueError("margin_close_time must be HH:MM")
                hh, mm = parts
                if not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
                    raise ValueError("margin_close_time must be HH:MM")

            if key == "margin_close_priority":
                chunks = [x.strip() for x in value.split(",") if x.strip()]
                if not chunks:
                    raise ValueError("margin_close_priority must not be empty")
                if len(set(chunks)) != len(chunks):
                    raise ValueError("margin_close_priority must be unique")
                if any(not x.isdigit() for x in chunks):
                    raise ValueError("margin_close_priority must contain numeric strategy IDs")

            if self._is_strategy_override_key(key):
                _, _, param = key.split(".", 2)
                base_rule = self._rules[param]
                number = float(value)
                if base_rule.min_value is not None and number < base_rule.min_value:
                    raise ValueError(f"{key} must be >= {base_rule.min_value}")
                if base_rule.max_value is not None and number > base_rule.max_value:
                    raise ValueError(f"{key} must be <= {base_rule.max_value}")

            self._values[key] = value

    def _is_strategy_override_key(self, key: str) -> bool:
        if not key.startswith("strategy."):
            return False
        parts = key.split(".")
        if len(parts) != 3:
            return False
        return parts[2] in self._strategy_overridable_keys
