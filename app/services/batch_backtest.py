from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from app.backtest.core import BacktestCore
from app.domain.models import Candle, Signal
from app.domain.universe_status import UniverseStatus
from app.repositories.backtest import BacktestRepository
from app.repositories.candle import CandleRepository
from app.repositories.market_data import CandleCollectionStateRepository
from app.repositories.universe import UniverseRepository
from app.risk.engine import RiskEngine


class BatchStrategy(Protocol):
    def generate(self, *, ticker: str, candles: list[Candle], now: datetime) -> Signal | None:
        raise NotImplementedError


StrategyFactory = Callable[[str, str, dict[str, object]], BatchStrategy]


@dataclass(frozen=True)
class BatchUniverseFilter:
    active_only: bool = True
    exclude_blocked: bool = True
    include_halted: bool = False
    tickers: list[str] | None = None


@dataclass(frozen=True)
class BatchCoveragePolicy:
    require_state_success: bool = False
    allow_partial_range: bool = False


@dataclass(frozen=True)
class BatchBacktestRequest:
    strategy_id: str
    timeframe: str
    start: datetime
    end: datetime
    universe_filter: BatchUniverseFilter = field(default_factory=BatchUniverseFilter)
    params: dict[str, object] = field(default_factory=dict)
    min_candles: int = 100
    coverage_policy: BatchCoveragePolicy = field(default_factory=BatchCoveragePolicy)


class BatchBacktestService:
    """유니버스 배치 백테스트 parent/child run 실행 서비스."""

    def __init__(
        self,
        *,
        session_factory,
        universe_repo: UniverseRepository | None = None,
        candle_repo: CandleRepository | None = None,
        state_repo: CandleCollectionStateRepository | None = None,
        backtest_repo: BacktestRepository | None = None,
        strategy_factory: StrategyFactory,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.universe_repo = universe_repo or UniverseRepository()
        self.candle_repo = candle_repo or CandleRepository()
        self.state_repo = state_repo or CandleCollectionStateRepository()
        self.backtest_repo = backtest_repo or BacktestRepository()
        self.strategy_factory = strategy_factory
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self._risk_engine = RiskEngine()

    async def run_batch(self, req: BatchBacktestRequest) -> str:
        batch_id = f"batch-{uuid4().hex}"
        created_at = self.now_fn()
        target_tickers = self._select_tickers(req)
        params = dict(req.params)
        slippage_pct = self._float_param(params, "slippage_pct", 0.0)
        parent_meta = {
            "source": "batch_backtest",
            "run_type": "batch_parent",
            "strategy_id": req.strategy_id,
            "timeframe": req.timeframe,
            "start": req.start.isoformat(),
            "end": req.end.isoformat(),
            "target_count": len(target_tickers),
            "universe_filter": self._universe_filter_meta(req.universe_filter),
            "coverage_policy": self._coverage_policy_meta(req.coverage_policy),
            "min_candles": req.min_candles,
            "params": params,
        }
        with self.session_factory() as db:
            self.backtest_repo.create_run(
                db,
                run_id=batch_id,
                name=f"batch:{req.strategy_id}:{req.timeframe}",
                strategy_id=req.strategy_id,
                timeframe=req.timeframe,
                start_at=req.start,
                end_at=req.end,
                params=params,
                slippage_pct=slippage_pct,
                commission_pct=self._float_param(params, "commission_pct", 0.0),
                status="running",
                meta=parent_meta,
                created_at=created_at,
                run_type="batch_parent",
            )

        items: list[dict[str, object]] = []
        for ticker in target_tickers:
            item = self._run_ticker_child(batch_id=batch_id, ticker=ticker, req=req, created_at=created_at)
            items.append(item)

        summary = self._aggregate_summary(items)
        completed_at = self.now_fn()
        parent_status = "completed_with_errors" if summary["failed_count"] else "completed"
        with self.session_factory() as db:
            self.backtest_repo.mark_completed(
                db,
                run_id=batch_id,
                summary=summary,
                completed_at=completed_at,
                trades=[],
                equity_points=[],
                status=parent_status,
            )
        return batch_id

    async def get_batch(self, batch_id: str) -> dict[str, object] | None:
        with self.session_factory() as db:
            row = self.backtest_repo.get_run(db, run_id=batch_id)
            if row is None:
                return None
            return self._run_to_dict(row)

    async def list_batches(self, *, limit: int = 50, offset: int = 0, status: str | None = None) -> list[dict[str, object]]:
        with self.session_factory() as db:
            rows = self.backtest_repo.list_runs(
                db,
                status=status,
                run_type="batch_parent",
                limit=limit,
                offset=offset,
            )
            return [self._run_to_dict(row) for row in rows]

    async def list_batch_items(self, batch_id: str) -> list[dict[str, object]]:
        with self.session_factory() as db:
            rows = self.backtest_repo.list_child_runs(db, parent_run_id=batch_id)
            return [self._run_to_dict(row) for row in rows]

    def count_batches(self, *, status: str | None = None) -> int:
        with self.session_factory() as db:
            return self.backtest_repo.count_runs(db, status=status, run_type="batch_parent")

    def _select_tickers(self, req: BatchBacktestRequest) -> list[str]:
        explicit = req.universe_filter.tickers
        if explicit is not None:
            return sorted({x.strip() for x in explicit if x and x.strip()})
        with self.session_factory() as db:
            if req.universe_filter.active_only and req.universe_filter.exclude_blocked and not req.universe_filter.include_halted:
                return self.universe_repo.list_trading_tickers(db, limit=20_000)
            rows = self.universe_repo.list_symbols(
                db,
                in_universe=True,
                is_active=True if req.universe_filter.active_only else None,
                is_blocked=False if req.universe_filter.exclude_blocked else None,
                limit=20_000,
            )
            tickers: list[str] = []
            for row in rows:
                if not req.universe_filter.include_halted and row.status == UniverseStatus.HALTED.value:
                    continue
                tickers.append(row.ticker)
            return tickers

    def _run_ticker_child(
        self,
        *,
        batch_id: str,
        ticker: str,
        req: BatchBacktestRequest,
        created_at: datetime,
    ) -> dict[str, object]:
        child_id = f"{batch_id}-{ticker}"
        params = dict(req.params)
        slippage_pct = self._float_param(params, "slippage_pct", 0.0)
        base_meta = {
            "source": "batch_backtest_child",
            "run_type": "batch_child",
            "parent_run_id": batch_id,
            "ticker": ticker,
            "strategy_id": req.strategy_id,
            "timeframe": req.timeframe,
            "start": req.start.isoformat(),
            "end": req.end.isoformat(),
            "min_candles": req.min_candles,
            "params": params,
        }
        with self.session_factory() as db:
            self.backtest_repo.create_run(
                db,
                run_id=child_id,
                name=ticker,
                strategy_id=req.strategy_id,
                timeframe=req.timeframe,
                start_at=req.start,
                end_at=req.end,
                params=params,
                slippage_pct=slippage_pct,
                commission_pct=self._float_param(params, "commission_pct", 0.0),
                status="running",
                meta=base_meta,
                created_at=created_at,
                run_type="batch_child",
                parent_run_id=batch_id,
                ticker=ticker,
            )
        try:
            coverage = self._coverage_snapshot(ticker=ticker, timeframe=req.timeframe)
            candles = self._load_candles(ticker=ticker, req=req)
            exclusion = self._exclusion_reason(candles=candles, coverage=coverage, req=req)
            if exclusion is not None:
                summary = {
                    "run_type": "batch_child",
                    "ticker": ticker,
                    "status": "excluded",
                    "exclude_reason": exclusion,
                    "candle_count": len(candles),
                    "signal_count": 0,
                    "trade_count": 0,
                    "coverage": coverage,
                }
                self._mark_child(child_id, summary=summary, status="excluded")
                return summary

            strategy = self.strategy_factory(req.strategy_id, req.timeframe, params)
            signals = self._build_signals(strategy=strategy, ticker=ticker, timeframe=req.timeframe, candles=candles)
            summary, trades, equity_points = self._simulate_child(
                ticker=ticker,
                candles=candles,
                signals=signals,
                params=params,
                slippage_pct=slippage_pct,
            )
            summary.update(
                {
                    "run_type": "batch_child",
                    "ticker": ticker,
                    "status": "completed",
                    "candle_count": len(candles),
                    "signal_count": len(signals),
                    "coverage": coverage,
                }
            )
            self._mark_child(child_id, summary=summary, status="completed", trades=trades, equity_points=equity_points)
            return summary
        except Exception as exc:  # noqa: BLE001 - batch must keep going per ticker
            completed_at = self.now_fn()
            with self.session_factory() as db:
                self.backtest_repo.mark_failed(db, run_id=child_id, error=str(exc), completed_at=completed_at)
            return {
                "run_type": "batch_child",
                "ticker": ticker,
                "status": "failed",
                "error": str(exc),
                "trade_count": 0,
                "signal_count": 0,
                "candle_count": 0,
            }

    def _coverage_snapshot(self, *, ticker: str, timeframe: str) -> dict[str, object] | None:
        with self.session_factory() as db:
            state = self.state_repo.get_state(db, ticker=ticker, timeframe=timeframe)
            if state is None:
                return None
            return {
                "first_candle_time": state.first_candle_time.isoformat() if state.first_candle_time else None,
                "last_candle_time": state.last_candle_time.isoformat() if state.last_candle_time else None,
                "row_count": state.row_count,
                "last_success_at": state.last_success_at.isoformat() if state.last_success_at else None,
                "last_error_at": state.last_error_at.isoformat() if state.last_error_at else None,
                "last_error": state.last_error,
                "consecutive_error_count": state.consecutive_error_count,
                "source": state.source,
            }

    def _load_candles(self, *, ticker: str, req: BatchBacktestRequest) -> list[Candle]:
        with self.session_factory() as db:
            rows = self.candle_repo.list_range(
                db,
                ticker=ticker,
                timeframe=req.timeframe,
                start=req.start,
                end=req.end,
                limit=200_000,
            )
        return [
            Candle(open=row.open, high=row.high, low=row.low, close=row.close, ts=row.candle_time, volume=row.volume)
            for row in rows
        ]

    def _exclusion_reason(
        self,
        *,
        candles: list[Candle],
        coverage: dict[str, object] | None,
        req: BatchBacktestRequest,
    ) -> str | None:
        if coverage is None:
            if req.coverage_policy.require_state_success:
                return "no_collection_state"
        elif req.coverage_policy.require_state_success and coverage.get("last_error"):
            return "collection_state_failed"
        if len(candles) < max(req.min_candles, 2):
            return "insufficient_candles"
        if not req.coverage_policy.allow_partial_range:
            first = candles[0].ts if candles else None
            last = candles[-1].ts if candles else None
            if first is None or first > req.start or last is None or last < req.end:
                return "coverage_gap"
        return None

    @staticmethod
    def _build_signals(
        *,
        strategy: BatchStrategy,
        ticker: str,
        timeframe: str,
        candles: list[Candle],
    ) -> list[Signal]:
        out: list[Signal] = []
        for idx in range(len(candles) - 1):
            window = candles[: idx + 1]
            signal = strategy.generate(ticker=ticker, candles=window, now=window[-1].ts)
            if signal is None:
                continue
            out.append(
                Signal(
                    index=idx,
                    side=signal.side,
                    ticker=ticker,
                    strategy_id=signal.strategy_id,
                    timeframe=signal.timeframe or timeframe,
                    price=signal.price,
                    signal_time=signal.signal_time,
                )
            )
        return out

    def _simulate_child(
        self,
        *,
        ticker: str,
        candles: list[Candle],
        signals: list[Signal],
        params: dict[str, object],
        slippage_pct: float,
    ) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
        core = BacktestCore(slippage_pct=slippage_pct)
        atr_period = max(int(float(params.get("atr_period", 14))), 1)
        stop_atr_mult = float(params.get("stop_atr_mult", 1.5))
        tp_atr_mult = float(params.get("tp_atr_mult", 2.0))
        trail_atr_mult = float(params.get("trail_atr_mult", 1.5))
        pnls: list[float] = []
        returns: list[float] = []
        trade_records: list[dict[str, object]] = []
        equity_points: list[dict[str, object]] = []
        cumulative_pnl = 0.0
        peak_equity = 0.0
        wins = 0
        losses = 0
        skipped = 0
        reasons: dict[str, int] = {}
        for signal in signals:
            try:
                pnl, ret, reason, exit_idx, exit_price = self._simulate_trade(
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
                continue
            pnls.append(pnl)
            returns.append(ret)
            record = self._trade_record(candles=candles, signal=signal, pnl=pnl, ret=ret, reason=reason, exit_idx=exit_idx, exit_price=exit_price)
            if record is not None:
                trade_records.append(record)
                cumulative_pnl += pnl
                peak_equity = max(peak_equity, cumulative_pnl)
                equity_points.append({"timestamp": record["exit_time"], "equity": cumulative_pnl, "drawdown": cumulative_pnl - peak_equity})
            reasons[reason] = reasons.get(reason, 0) + 1
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
        trade_count = len(pnls)
        total_pnl = sum(pnls)
        gross_profit = sum(x for x in pnls if x > 0)
        gross_loss = abs(sum(x for x in pnls if x < 0))
        summary = {
            "ticker": ticker,
            "trade_count": trade_count,
            "wins": wins,
            "losses": losses,
            "skipped": skipped,
            "win_rate": wins / trade_count if trade_count else 0.0,
            "total_pnl": total_pnl,
            "avg_pnl": total_pnl / trade_count if trade_count else 0.0,
            "total_return": sum(returns),
            "total_return_pct": sum(returns) * 100.0,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "mdd": self._max_drawdown(returns),
            "exit_reasons": reasons,
        }
        return summary, trade_records, equity_points

    def _mark_child(
        self,
        child_id: str,
        *,
        summary: dict[str, object],
        status: str,
        trades: list[dict[str, object]] | None = None,
        equity_points: list[dict[str, object]] | None = None,
    ) -> None:
        with self.session_factory() as db:
            self.backtest_repo.mark_completed(
                db,
                run_id=child_id,
                summary=summary,
                completed_at=self.now_fn(),
                trades=trades or [],
                equity_points=equity_points or [],
                status=status,
            )

    @staticmethod
    def _aggregate_summary(items: list[dict[str, object]]) -> dict[str, object]:
        completed = [x for x in items if x.get("status") == "completed"]
        excluded = [x for x in items if x.get("status") == "excluded"]
        failed = [x for x in items if x.get("status") == "failed"]
        trade_count = sum(int(x.get("trade_count") or 0) for x in completed)
        wins = sum(int(x.get("wins") or 0) for x in completed)
        total_pnl = sum(float(x.get("total_pnl") or 0.0) for x in completed)
        gross_profit = sum(float(str(x.get("gross_profit") or 0.0)) for x in completed)
        gross_loss = sum(float(str(x.get("gross_loss") or 0.0)) for x in completed)
        mdd = max((float(str(x.get("mdd") or 0.0)) for x in completed), default=0.0)
        exclude_reasons: dict[str, int] = {}
        for item in excluded:
            reason = str(item.get("exclude_reason") or "unknown")
            exclude_reasons[reason] = exclude_reasons.get(reason, 0) + 1
        return {
            "run_type": "batch_parent",
            "target_count": len(items),
            "completed_count": len(completed),
            "failed_count": len(failed),
            "excluded_count": len(excluded),
            "no_signal_count": sum(1 for x in completed if int(x.get("signal_count") or 0) == 0),
            "trade_count": trade_count,
            "win_rate": wins / trade_count if trade_count else 0.0,
            "total_pnl": total_pnl,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else None,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "mdd": mdd,
            "children": {"completed": len(completed), "failed": len(failed), "excluded": len(excluded)},
            "exclude_reasons": exclude_reasons,
            "items": items,
        }

    def _simulate_trade(self, **kwargs) -> tuple[float, float, str, int, float]:
        from app.services.backtest_jobs import BacktestJobService

        helper = BacktestJobService(session_factory=None, backtest_repo=None)
        return helper._simulate_trade(**kwargs)

    @staticmethod
    def _trade_record(**kwargs) -> dict[str, object] | None:
        from app.services.backtest_jobs import BacktestJobService

        return BacktestJobService._trade_record(**kwargs)

    @staticmethod
    def _run_to_dict(row) -> dict[str, object]:
        return {
            "job_id": row.id,
            "status": row.status,
            "progress": 100 if row.status in {"completed", "completed_with_errors", "failed", "excluded"} else 0,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "result": row.summary_json if row.status in {"completed", "completed_with_errors", "excluded"} else None,
            "error": row.error,
            "meta": dict(row.meta_json or {}),
            "run_type": row.run_type,
            "parent_run_id": row.parent_run_id,
            "ticker": row.ticker,
            "persistent": True,
        }

    @staticmethod
    def _universe_filter_meta(value: BatchUniverseFilter) -> dict[str, object]:
        return {
            "active_only": value.active_only,
            "exclude_blocked": value.exclude_blocked,
            "include_halted": value.include_halted,
            "tickers": value.tickers,
        }

    @staticmethod
    def _coverage_policy_meta(value: BatchCoveragePolicy) -> dict[str, object]:
        return {"require_state_success": value.require_state_success, "allow_partial_range": value.allow_partial_range}

    @staticmethod
    def _float_param(params: dict[str, object], key: str, default: float) -> float:
        try:
            return float(params.get(key, default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _max_drawdown(returns: list[float]) -> float:
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for ret in returns:
            equity *= max(0.0, 1.0 + ret)
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
        return max_dd
