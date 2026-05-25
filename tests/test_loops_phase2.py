from app.core.config import ConfigManager
from app.loops.core import LoopCMaintainer, LoopAPositionManager
from app.risk.engine import PositionExposure, RiskEngine


class FakeMaintenanceService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def refresh_universe(self) -> None:
        self.calls.append("universe")

    def optimize_parameters(self) -> None:
        self.calls.append("optimize")

    def aggregate_daily_performance(self) -> None:
        self.calls.append("perf")


def test_loop_c_maintenance_responsibility():
    svc = FakeMaintenanceService()
    loop_c = LoopCMaintainer(svc)
    loop_c.run_once()
    assert svc.calls == ["universe", "optimize", "perf"]


def test_loop_a_margin_close_resolution():
    cfg = ConfigManager(
        initial={
            "daily_base_capital": "150",
            "margin_close_priority": "1,2,3,5,4",
        }
    )
    manager = LoopAPositionManager(risk_engine=RiskEngine(), ordering_repo=object(), config=cfg)
    exposures = [
        PositionExposure(position_id=1, strategy_id="4", market_value=100),
        PositionExposure(position_id=2, strategy_id="1", market_value=100),
        PositionExposure(position_id=3, strategy_id="2", market_value=100),
    ]
    to_close = manager.resolve_margin_forced_close(exposures)
    assert to_close == [2, 3]
