from app.core.config_manager import ConfigManager
from app.risk.engine import RiskEngine
from tests.utils import build_session, reset_manager


def test_max_positions_threshold():
    manager = reset_manager()
    with build_session() as db:
        manager.load(db)
        manager.set(db, "max_positions", "2", changed_by="test")
        engine = RiskEngine(manager)

        assert engine.can_open_new_position(0) is True
        assert engine.can_open_new_position(1) is True
        assert engine.can_open_new_position(2) is False
