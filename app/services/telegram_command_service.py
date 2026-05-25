from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from app.services.runtime_state import PendingConfigChange, RuntimeState


class ConfigWriter(Protocol):
    def get_all(self) -> dict[str, str]:
        raise NotImplementedError

    def set(self, *, key: str, value: str, changed_by: str = "system") -> None:
        raise NotImplementedError


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str


class TelegramCommandService:
    def __init__(
        self,
        *,
        config: ConfigWriter,
        runtime: RuntimeState,
        report_provider: Callable[[], str] | None = None,
        paper_report_provider: Callable[[], dict[str, object]] | None = None,
        backtest_status_provider: Callable[[], dict[str, object]] | None = None,
        runtime_status_provider: Callable[[], dict[str, object]] | None = None,
    ) -> None:
        self.config = config
        self.runtime = runtime
        self.report_provider = report_provider
        self.paper_report_provider = paper_report_provider
        self.backtest_status_provider = backtest_status_provider
        self.runtime_status_provider = runtime_status_provider
        self.confirm_required_keys = {
            "position_size_max_pct",
            "position_size_min_pct",
            "risk_per_trade_pct",
            "daily_loss_pct",
            "stop_count",
            "cooldown_hours",
            "max_positions",
            "margin_ratio",
            "order_cancel_minutes",
        }
        self.telegram_blocked_keys = {
            "atr_period",
            "stop_atr_mult",
            "tp_atr_mult",
            "trail_atr_mult",
            "margin_close_priority",
        }

    def handle(self, command: str) -> CommandResult:
        text = command.strip()
        if not text:
            return CommandResult(ok=False, message="명령어가 비어 있습니다.")

        if text in {"/pause", "/pause entry"}:
            self.runtime.pause_entry()
            return CommandResult(ok=True, message="진입 자동매매를 일시중지했습니다.")
        if text == "/pause all":
            self.runtime.pause_all()
            return CommandResult(ok=True, message="전체 자동매매를 일시중지했습니다.")
        if text == "/resume":
            self.runtime.resume()
            return CommandResult(ok=True, message="자동매매를 재개했습니다.")
        if text == "/status":
            pending = self.runtime.pending_change.key if self.runtime.pending_change else "없음"
            msg = (
                f"진입중지={self.runtime.entry_paused}, "
                f"전체중지={self.runtime.all_paused}, "
                f"비상정지={self.runtime.halted}, "
                f"변경대기={pending}"
            )
            runtime_suffix = self._runtime_status_snippet()
            if runtime_suffix is not None:
                msg += f", {runtime_suffix}"
            backtest_suffix = self._backtest_status_snippet()
            if backtest_suffix is not None:
                msg += f", {backtest_suffix}"
            return CommandResult(ok=True, message=msg)
        if text == "/settings":
            pairs = self.config.get_all()
            condensed = ", ".join(f"{k}={v}" for k, v in sorted(pairs.items()))
            return CommandResult(ok=True, message=condensed)
        if text == "/report":
            if self.report_provider is None:
                return CommandResult(ok=False, message="리포트를 생성할 수 없습니다.")
            msg = self.report_provider()
            suffix = self._backtest_status_snippet()
            if suffix is not None:
                msg = f"{msg}\n{suffix}"
            return CommandResult(ok=True, message=msg)
        if text == "/paper_report":
            return self._handle_paper_report()
        if text == "/confirm":
            return self._confirm_pending()
        if text.startswith("/set "):
            return self._handle_set(text)
        if text.startswith("/close "):
            return self._handle_close(text)
        return CommandResult(ok=False, message=f"지원하지 않는 명령어입니다: {text}")

    def _handle_set(self, text: str) -> CommandResult:
        parts = text.split(maxsplit=2)
        if len(parts) != 3:
            return CommandResult(ok=False, message="사용법: /set [키] [값]")
        _, key, value = parts
        if key in self.telegram_blocked_keys or key.startswith("strategy."):
            return CommandResult(ok=False, message=f"{key} 항목은 웹 UI에서만 변경할 수 있습니다.")

        if key in self.confirm_required_keys:
            self.runtime.pending_change = PendingConfigChange(key=key, value=value, changed_by="telegram")
            return CommandResult(ok=True, message=f"확인 대기 중: {key}={value}. /confirm 을 실행하세요.")

        try:
            self.config.set(key=key, value=value, changed_by="telegram")
        except (KeyError, ValueError) as exc:
            return CommandResult(ok=False, message=str(exc))
        return CommandResult(ok=True, message=f"설정을 변경했습니다: {key}={value}")

    def _confirm_pending(self) -> CommandResult:
        pending = self.runtime.pending_change
        if pending is None:
            return CommandResult(ok=False, message="확인 대기 중인 변경이 없습니다.")

        try:
            self.config.set(key=pending.key, value=pending.value, changed_by=pending.changed_by)
        except (KeyError, ValueError) as exc:
            return CommandResult(ok=False, message=str(exc))
        self.runtime.pending_change = None
        return CommandResult(ok=True, message="대기 중이던 설정 변경을 적용했습니다.")

    def _handle_close(self, text: str) -> CommandResult:
        if text == "/close all":
            return CommandResult(ok=True, message="전체 포지션 청산 요청을 접수했습니다.")
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            return CommandResult(ok=False, message="사용법: /close [종목코드]|all")
        ticker = parts[1].strip()
        if not ticker:
            return CommandResult(ok=False, message="사용법: /close [종목코드]|all")
        return CommandResult(ok=True, message=f"{ticker} 종목 청산 요청을 접수했습니다.")

    def _handle_paper_report(self) -> CommandResult:
        if self.paper_report_provider is None:
            return CommandResult(ok=False, message="페이퍼 리포트를 생성할 수 없습니다.")
        report = self.paper_report_provider()
        if not report.get("ok"):
            return CommandResult(ok=False, message=f"페이퍼 리포트 생성 실패: {report.get('error', '알수없음')}")
        passed = bool(report.get("passed"))
        metrics = report.get("metrics", {})
        msg = (
            f"페이퍼합격여부={passed}, "
            f"신호수={metrics.get('total_signals', 0)}, "
            f"승률={metrics.get('win_rate', 0):.3f}, "
            f"샤프={metrics.get('sharpe_ratio', 0):.3f}, "
            f"최대낙폭={metrics.get('mdd', 0):.3f}, "
            f"오류율={metrics.get('error_rate', 0):.6f}"
        )
        suffix = self._backtest_status_snippet()
        if suffix is not None:
            msg += f", {suffix}"
        return CommandResult(ok=True, message=msg)

    def _backtest_status_snippet(self) -> str | None:
        if self.backtest_status_provider is None:
            return None
        try:
            st = self.backtest_status_provider()
        except Exception:  # noqa: BLE001
            return "자동백테스트상태=사용불가, 자동백테스트작업=None"
        return (
            f"자동백테스트상태={st.get('last_status', '알수없음')}, "
            f"자동백테스트작업={st.get('last_job_id', '알수없음')}"
        )

    def _runtime_status_snippet(self) -> str | None:
        if self.runtime_status_provider is None:
            return None
        try:
            st = self.runtime_status_provider()
        except Exception:  # noqa: BLE001
            return "루프실행=알수없음, 루프사이클=알수없음, 루프최근지연ms=알수없음"
        return (
            f"루프실행={st.get('loop_running')}, "
            f"루프사이클={st.get('loop_cycles')}, "
            f"루프최근지연ms={st.get('loop_last_ms')}"
        )
