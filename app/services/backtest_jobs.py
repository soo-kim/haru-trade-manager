from __future__ import annotations

import asyncio
import math
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from app.backtest.core import BacktestCore
from app.domain.models import Candle, Signal
from app.risk.engine import RiskEngine


class AlertSink(Protocol):
    async def send_message(self, text: str) -> bool:
        raise NotImplementedError


class BacktestJobService:
    """비동기 백테스트 실행과 진행률 추적을 담당한다."""

    def __init__(self, *, alert_sink: AlertSink | None = None, max_jobs: int = 200) -> None:
        self.alert_sink = alert_sink
        self.max_jobs = max_jobs
        self._jobs: dict[str, dict[str, object]] = {}
        self._lock = asyncio.Lock()
        self._risk_engine = RiskEngine()

    async def start_job(
        self,
        *,
        candles: list[Candle],
        signals: list[Signal],
        slippage_pct: float = 0.05,
        meta: dict[str, object] | None = None,
    ) -> str:
        job_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        async with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "progress": 0,
                "created_at": now,
                "started_at": None,
                "completed_at": None,
                "result": None,
                "error": None,
                "meta": dict(meta or {}),
            }
            self._trim_jobs()

        asyncio.create_task(
            self._run_job(job_id=job_id, candles=candles, signals=signals, slippage_pct=slippage_pct),
            name=f"backtest-job-{job_id}",
        )
        return job_id

    async def get_job(self, job_id: str) -> dict[str, object] | None:
        async with self._lock:
            row = self._jobs.get(job_id)
            return None if row is None else dict(row)

    async def list_jobs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[dict[str, object]]:
        async with self._lock:
            rows = list(self._jobs.values())
        if status is not None and status.strip():
            rows = [x for x in rows if x.get("status") == status]
        rows.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        start = max(offset, 0)
        end = start + max(limit, 0)
        return [dict(x) for x in rows[start:end]]

    async def count_jobs(self, *, status: str | None = None) -> int:
        async with self._lock:
            rows = list(self._jobs.values())
        if status is not None and status.strip():
            rows = [x for x in rows if x.get("status") == status]
        return len(rows)

    async def _run_job(self, *, job_id: str, candles: list[Candle], signals: list[Signal], slippage_pct: float) -> None:
        async with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                return
            row["status"] = "running"
            row["started_at"] = datetime.now(timezone.utc).isoformat()
            meta = dict(row.get("meta", {})) if isinstance(row.get("meta"), dict) else {}

        try:
            core = BacktestCore(slippage_pct=slippage_pct)
            atr_period = max(int(float(meta.get("atr_period", 14))), 1)
            stop_atr_mult = float(meta.get("stop_atr_mult", 1.5))
            tp_atr_mult = float(meta.get("tp_atr_mult", 2.0))
            trail_atr_mult = float(meta.get("trail_atr_mult", 1.5))
            pnls: list[float] = []
            returns: list[float] = []
            reasons: dict[str, int] = {}
            wins = 0
            losses = 0
            skipped = 0
            total = max(len(signals), 1)

            for idx, signal in enumerate(signals):
                await asyncio.sleep(0)
                try:
                    pnl, ret, reason = self._simulate_trade(
                        core=core,
                        candles=candles,
                        signal=signal,
                        atr_period=atr_period,
                        stop_atr_mult=stop_atr_mult,
                        tp_atr_mult=tp_atr_mult,
                        trail_atr_mult=trail_atr_mult,
                    )
                except ValueError:
                    skipped += 1
                    await self._update_progress(job_id=job_id, progress=int(((idx + 1) / total) * 100))
                    continue

                pnls.append(pnl)
                returns.append(ret)
                reasons[reason] = reasons.get(reason, 0) + 1
                if pnl > 0:
                    wins += 1
                elif pnl < 0:
                    losses += 1

                await self._update_progress(job_id=job_id, progress=int(((idx + 1) / total) * 100))

            trade_count = len(pnls)
            total_pnl = sum(pnls)
            avg_pnl = total_pnl / trade_count if trade_count else 0.0
            win_rate = wins / trade_count if trade_count else 0.0
            gross_profit = sum(x for x in pnls if x > 0)
            gross_loss = abs(sum(x for x in pnls if x < 0))
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None
            total_return = sum(returns)
            result = {
                "trade_count": trade_count,
                "wins": wins,
                "losses": losses,
                "skipped": skipped,
                "win_rate": win_rate,
                "total_pnl": total_pnl,
                "avg_pnl": avg_pnl,
                "expectancy": avg_pnl,
                "expectancy_r": (sum(returns) / trade_count) if trade_count else 0.0,
                "total_return": total_return,
                "total_return_pct": total_return * 100.0,
                "sharpe_ratio": self._sharpe_ratio(returns),
                "mdd": self._max_drawdown(returns),
                "gross_profit": gross_profit,
                "gross_loss": gross_loss,
                "profit_factor": profit_factor,
                "exit_reasons": reasons,
                "atr_period": atr_period,
                "stop_atr_mult": stop_atr_mult,
                "tp_atr_mult": tp_atr_mult,
                "trail_atr_mult": trail_atr_mult,
            }

            should_notify = True
            async with self._lock:
                row = self._jobs.get(job_id)
                if row is None:
                    return
                row["status"] = "completed"
                row["progress"] = 100
                row["result"] = result
                row["completed_at"] = datetime.now(timezone.utc).isoformat()
                should_notify = self._should_notify_completion(row)

            if should_notify and self.alert_sink is not None:
                await self.alert_sink.send_message(
                    f"[백테스트 완료] 작업={job_id[:8]} 거래수={trade_count} 승률={win_rate:.3f}"
                )
        except Exception as exc:  # noqa: BLE001
            should_notify = True
            async with self._lock:
                row = self._jobs.get(job_id)
                if row is None:
                    return
                row["status"] = "failed"
                row["error"] = str(exc)
                row["completed_at"] = datetime.now(timezone.utc).isoformat()
                should_notify = self._should_notify_completion(row)
            if should_notify and self.alert_sink is not None:
                await self.alert_sink.send_message(f"[백테스트 실패] 작업={job_id[:8]} 오류={exc}")

    async def _update_progress(self, *, job_id: str, progress: int) -> None:
        async with self._lock:
            row = self._jobs.get(job_id)
            if row is None:
                return
            row["progress"] = max(0, min(progress, 100))

    def _trim_jobs(self) -> None:
        overflow = len(self._jobs) - self.max_jobs
        if overflow <= 0:
            return
        keys = sorted(self._jobs, key=lambda x: str(self._jobs[x].get("created_at", "")))
        for key in keys[:overflow]:
            self._jobs.pop(key, None)

    def _compute_atr(self, *, candles: list[Candle], signal_index: int, atr_period: int) -> float:
        start = max(0, signal_index - atr_period + 1)
        window = candles[start : signal_index + 1]
        if not window:
            return 1.0
        highs = [float(x.high) for x in window]
        lows = [float(x.low) for x in window]
        closes = [float(x.close) for x in window]
        atr = self._risk_engine.compute_atr(highs=highs, lows=lows, closes=closes)
        return max(float(atr), 1e-9)

    def _simulate_trade(
        self,
        *,
        core: BacktestCore,
        candles: list[Candle],
        signal: Signal,
        atr_period: int,
        stop_atr_mult: float,
        tp_atr_mult: float,
        trail_atr_mult: float,
    ) -> tuple[float, float, str]:
        entry_idx = signal.index + 1
        if entry_idx >= len(candles):
            raise ValueError("N+1 candle required")
        entry = core.entry_price_n_plus_one_open(candles, signal)
        if entry <= 0:
            raise ValueError("invalid_entry_price")
        atr = self._compute_atr(candles=candles, signal_index=signal.index, atr_period=atr_period)

        if signal.side == "sell":
            return self._simulate_short_trade(
                candles=candles,
                entry_idx=entry_idx,
                entry_price=entry,
                atr=atr,
                stop_atr_mult=stop_atr_mult,
                tp_atr_mult=tp_atr_mult,
                trail_atr_mult=trail_atr_mult,
            )
        return self._simulate_long_trade(
            candles=candles,
            entry_idx=entry_idx,
            entry_price=entry,
            atr=atr,
            stop_atr_mult=stop_atr_mult,
            tp_atr_mult=tp_atr_mult,
            trail_atr_mult=trail_atr_mult,
        )

    @staticmethod
    def _simulate_long_trade(
        *,
        candles: list[Candle],
        entry_idx: int,
        entry_price: float,
        atr: float,
        stop_atr_mult: float,
        tp_atr_mult: float,
        trail_atr_mult: float,
    ) -> tuple[float, float, str]:
        stop_price = max(entry_price - (atr * stop_atr_mult), 0.0)
        take_profit_price = entry_price + (atr * tp_atr_mult)
        remaining = 1.0
        realized = 0.0
        state = "OPEN"
        highest: float | None = None
        trailing_stop: float | None = None
        reason = "end_of_data"

        for candle in candles[entry_idx:]:
            if remaining <= 0:
                break
            if state == "OPEN":
                hit_stop = candle.low <= stop_price
                hit_tp = candle.high >= take_profit_price
                if hit_stop:
                    realized += (stop_price - entry_price) * remaining
                    remaining = 0.0
                    reason = "stop_loss"
                    break
                if hit_tp:
                    close_qty = remaining / 2.0
                    realized += (take_profit_price - entry_price) * close_qty
                    remaining -= close_qty
                    state = "HALF_CLOSED"
                    highest = max(candle.high, take_profit_price)
                    trailing_stop = max(highest - (atr * trail_atr_mult), 0.0)
                    # 동일 봉에서 고점 형성 직후 급락한 경우를 반영해 트레일링 즉시 청산을 허용한다.
                    if candle.low <= trailing_stop:
                        realized += (trailing_stop - entry_price) * remaining
                        remaining = 0.0
                        reason = "trailing_stop"
                        break
                    continue
            else:
                highest = max(highest or candle.high, candle.high)
                trailing_stop = max(highest - (atr * trail_atr_mult), 0.0)
                if candle.low <= trailing_stop:
                    realized += (trailing_stop - entry_price) * remaining
                    remaining = 0.0
                    reason = "trailing_stop"
                    break

        if remaining > 0:
            exit_price = candles[-1].close
            realized += (exit_price - entry_price) * remaining
            reason = "end_of_data"
        return realized, (realized / entry_price) if entry_price > 0 else 0.0, reason

    @staticmethod
    def _simulate_short_trade(
        *,
        candles: list[Candle],
        entry_idx: int,
        entry_price: float,
        atr: float,
        stop_atr_mult: float,
        tp_atr_mult: float,
        trail_atr_mult: float,
    ) -> tuple[float, float, str]:
        stop_price = entry_price + (atr * stop_atr_mult)
        take_profit_price = max(entry_price - (atr * tp_atr_mult), 0.0)
        remaining = 1.0
        realized = 0.0
        state = "OPEN"
        lowest: float | None = None
        trailing_stop: float | None = None
        reason = "end_of_data"

        for candle in candles[entry_idx:]:
            if remaining <= 0:
                break
            if state == "OPEN":
                hit_stop = candle.high >= stop_price
                hit_tp = candle.low <= take_profit_price
                if hit_stop:
                    realized += (entry_price - stop_price) * remaining
                    remaining = 0.0
                    reason = "stop_loss"
                    break
                if hit_tp:
                    close_qty = remaining / 2.0
                    realized += (entry_price - take_profit_price) * close_qty
                    remaining -= close_qty
                    state = "HALF_CLOSED"
                    lowest = min(candle.low, take_profit_price)
                    trailing_stop = lowest + (atr * trail_atr_mult)
                    if candle.high >= trailing_stop:
                        realized += (entry_price - trailing_stop) * remaining
                        remaining = 0.0
                        reason = "trailing_stop"
                        break
                    continue
            else:
                lowest = min(lowest or candle.low, candle.low)
                trailing_stop = lowest + (atr * trail_atr_mult)
                if candle.high >= trailing_stop:
                    realized += (entry_price - trailing_stop) * remaining
                    remaining = 0.0
                    reason = "trailing_stop"
                    break

        if remaining > 0:
            exit_price = candles[-1].close
            realized += (entry_price - exit_price) * remaining
            reason = "end_of_data"
        return realized, (realized / entry_price) if entry_price > 0 else 0.0, reason

    @staticmethod
    def _should_notify_completion(row: dict[str, object]) -> bool:
        meta = row.get("meta")
        if not isinstance(meta, dict):
            return True
        source = str(meta.get("source", "")).strip().lower()
        # 대시보드 단건 수동 백테스트는 실행시간이 짧아 완료 알림을 생략한다.
        if source == "dashboard_manual":
            return False
        return True

    @staticmethod
    def _sharpe_ratio(returns: list[float]) -> float:
        if len(returns) < 2:
            return 0.0
        avg = sum(returns) / len(returns)
        variance = sum((x - avg) ** 2 for x in returns) / len(returns)
        std = math.sqrt(variance)
        if std == 0:
            return 10.0 if avg > 0 else 0.0
        return avg / std * math.sqrt(len(returns))

    @staticmethod
    def _max_drawdown(returns: list[float]) -> float:
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for r in returns:
            equity *= max(0.0, 1.0 + r)
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
        return max_dd
