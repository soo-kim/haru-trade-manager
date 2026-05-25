from __future__ import annotations

from dataclasses import dataclass

from app.core.config import ConfigManager
from app.core.rate_limited_client import RateLimitedClient
from app.core.settings import settings
from app.db.session import SessionLocal
from app.integrations.telegram.client import TelegramClient
from app.repositories.candle import CandleRepository
from app.repositories.config import ConfigRepository
from app.repositories.ordering import OrderingRepository
from app.repositories.paper import PaperRepository
from app.repositories.universe import UniverseRepository
from app.services.auth import OtpAuthService
from app.services.auth_audit import AuthAuditService
from app.services.backtest_jobs import BacktestJobService
from app.services.config_service import ConfigChangeHook, ConfigService
from app.services.loop_background import LoopBackgroundRunner
from app.services.paper_report import PaperReportService
from app.services.performance import PerformanceService
from app.services.runtime_factory import build_runtime_bundle
from app.services.runtime_safety import RuntimeSafetyManager
from app.services.runtime_state import RuntimeState
from app.services.strategy_performance import StrategyPerformanceService


@dataclass
class CoreServices:
    config_manager: ConfigManager
    alert_sink: TelegramClient | None
    config_service: ConfigService
    runtime_state: RuntimeState
    safety_manager: RuntimeSafetyManager
    runtime_bundle: object
    loop_runtime: object
    loop_background: LoopBackgroundRunner
    performance_service: PerformanceService
    backtest_service: BacktestJobService
    auth_audit_service: AuthAuditService
    auth_service: OtpAuthService
    universe_repo: UniverseRepository
    candle_repo: CandleRepository
    ordering_repo: OrderingRepository
    config_repo: ConfigRepository
    paper_repo: PaperRepository
    strategy_performance_service: StrategyPerformanceService
    paper_report_service: PaperReportService


def _build_alert_sink() -> TelegramClient | None:
    if not settings.telegram_token or not settings.telegram_chat_id:
        return None
    return TelegramClient(RateLimitedClient())


def build_core_services(*, on_config_change: ConfigChangeHook | None = None) -> CoreServices:
    config_manager = ConfigManager()
    alert_sink = _build_alert_sink()
    config_service = ConfigService(
        config_manager,
        session_factory=SessionLocal,
        on_change=on_config_change,
    )
    runtime_state = RuntimeState()
    safety_manager = RuntimeSafetyManager(runtime=runtime_state, alert_sink=alert_sink)
    runtime_bundle = build_runtime_bundle(config=config_manager, safety=safety_manager)
    loop_runtime = runtime_bundle.coordinator
    loop_background = LoopBackgroundRunner(coordinator=loop_runtime, interval_seconds=1.0)
    performance_service = PerformanceService(session_factory=SessionLocal)
    backtest_service = BacktestJobService(alert_sink=alert_sink)
    auth_audit_service = AuthAuditService(session_factory=SessionLocal)
    auth_service = OtpAuthService(
        alert_sink=alert_sink,
        audit_sink=auth_audit_service,
    )
    universe_repo = UniverseRepository()
    candle_repo = CandleRepository()
    ordering_repo = OrderingRepository()
    config_repo = ConfigRepository(config_manager)
    paper_repo = PaperRepository()
    strategy_performance_service = StrategyPerformanceService(session_factory=SessionLocal)
    paper_report_service = PaperReportService(
        session_factory=SessionLocal,
        runtime_health_provider=loop_runtime.health_snapshot,
        safety_manager=safety_manager,
    )
    return CoreServices(
        config_manager=config_manager,
        alert_sink=alert_sink,
        config_service=config_service,
        runtime_state=runtime_state,
        safety_manager=safety_manager,
        runtime_bundle=runtime_bundle,
        loop_runtime=loop_runtime,
        loop_background=loop_background,
        performance_service=performance_service,
        backtest_service=backtest_service,
        auth_audit_service=auth_audit_service,
        auth_service=auth_service,
        universe_repo=universe_repo,
        candle_repo=candle_repo,
        ordering_repo=ordering_repo,
        config_repo=config_repo,
        paper_repo=paper_repo,
        strategy_performance_service=strategy_performance_service,
        paper_report_service=paper_report_service,
    )
