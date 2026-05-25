from __future__ import annotations

from datetime import date, timedelta
from typing import Callable, Protocol

from app.services.runtime_safety import RuntimeEvent, RuntimeSafetyManager


class AlertSink(Protocol):
    async def send_message(self, text: str) -> bool:
        raise NotImplementedError


class DailyIncidentReporter:
    def __init__(
        self,
        *,
        safety: RuntimeSafetyManager,
        alert_sink: AlertSink | None = None,
        backtest_status_provider: Callable[[], dict[str, object]] | None = None,
        strategy_summary_provider: Callable[[], dict[str, object]] | None = None,
    ) -> None:
        self.safety = safety
        self.alert_sink = alert_sink
        self.backtest_status_provider = backtest_status_provider
        self.strategy_summary_provider = strategy_summary_provider
        self._last_sent_day: date | None = None
        self._last_weekly_sent_key: str | None = None

    def build_report_text(self, day: date) -> str:
        events = self.safety.events_on(day)
        return self._build_template(title="[일일 운영 리포트]", label=day.isoformat(), events=events)

    def build_weekly_report_text(self, end_day: date, days: int = 7) -> str:
        start_day = end_day - timedelta(days=max(days - 1, 0))
        events: list[RuntimeEvent] = []
        for i in range(max(days, 1)):
            d = start_day + timedelta(days=i)
            events.extend(self.safety.events_on(d))
        label = f"{start_day.isoformat()}~{end_day.isoformat()}"
        return self._build_template(title="[주간 운영 리포트]", label=label, events=events)

    async def send_report(self, day: date) -> bool:
        if self.alert_sink is None:
            return False
        text = self.build_report_text(day)
        ok = await self.alert_sink.send_message(text)
        if ok:
            self._last_sent_day = day
        return ok

    async def send_report_once_per_day(self, day: date) -> bool:
        if self._last_sent_day == day:
            return False
        return await self.send_report(day)

    async def send_weekly_report(self, end_day: date, days: int = 7) -> bool:
        if self.alert_sink is None:
            return False
        text = self.build_weekly_report_text(end_day, days=days)
        ok = await self.alert_sink.send_message(text)
        if ok:
            iso = end_day.isocalendar()
            self._last_weekly_sent_key = f"{iso.year}-W{iso.week:02d}"
        return ok

    async def send_weekly_report_once_per_week(self, end_day: date, days: int = 7) -> bool:
        iso = end_day.isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        if self._last_weekly_sent_key == key:
            return False
        return await self.send_weekly_report(end_day, days=days)

    def _build_template(self, *, title: str, label: str, events: list[RuntimeEvent]) -> str:
        lines = [f"{title} {label} - 장애 건수: {len(events)}"]
        if events:
            lines.extend(self._summaries(events))
        lines.extend(self._backtest_lines())
        lines.extend(self._strategy_lines())
        return "\n".join(lines)

    @staticmethod
    def _summaries(events: list[RuntimeEvent]) -> list[str]:
        grouped: dict[str, int] = {}
        for event in events:
            grouped[event.code] = grouped.get(event.code, 0) + 1
        return [f"- {code}: {count}" for code, count in sorted(grouped.items())]

    def _backtest_lines(self) -> list[str]:
        if self.backtest_status_provider is None:
            return []
        try:
            status = self.backtest_status_provider()
        except Exception:  # noqa: BLE001
            return ["- 자동백테스트: 사용불가"]

        base = (
            f"- 자동백테스트: 활성화={status.get('enabled')} "
            f"최근상태={status.get('last_status')} "
            f"최근작업={status.get('last_job_id')}"
        )
        lines = [base]
        snap = status.get("last_job_snapshot")
        if isinstance(snap, dict):
            result = snap.get("result")
            if isinstance(result, dict):
                lines.append(
                    "- 자동백테스트결과: "
                    f"거래수={result.get('trade_count')} "
                    f"승률={result.get('win_rate')} "
                    f"손익={result.get('total_pnl')} "
                    f"샤프={result.get('sharpe_ratio')} "
                    f"최대낙폭={result.get('mdd')}"
                )
            elif snap.get("error"):
                lines.append(f"- 자동백테스트오류: {snap.get('error')}")
        return lines

    def _strategy_lines(self) -> list[str]:
        if self.strategy_summary_provider is None:
            return []
        try:
            data = self.strategy_summary_provider()
        except Exception:  # noqa: BLE001
            return ["- 전략요약: 사용불가"]
        if not data.get("ok"):
            return [f"- 전략요약오류: {data.get('error', '알수없음')}"]

        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            return ["- 전략요약: 데이터없음"]

        top = items[0]
        bottom = items[-1]
        lines = [
            "- 상위전략: "
            f"{top.get('strategy_id')} "
            f"손익={top.get('total_pnl')} "
            f"승률={top.get('win_rate')} "
            f"기대값={top.get('expectancy')}",
        ]
        if len(items) > 1:
            lines.append(
                "- 하위전략: "
                f"{bottom.get('strategy_id')} "
                f"손익={bottom.get('total_pnl')} "
                f"승률={bottom.get('win_rate')} "
                f"기대값={bottom.get('expectancy')}",
            )
        return lines
