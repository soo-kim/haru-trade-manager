from sqlalchemy import select

from app.core.config_manager import ConfigManager
from app.db.models.config import ConfigHistory
from tests.utils import build_session, reset_manager


def test_load_populates_default_configs():
    manager = reset_manager()
    with build_session() as db:
        manager.load(db)
        assert manager.get("max_positions") == "10"


def test_set_valid_value_updates_cache_and_history():
    manager = reset_manager()
    with build_session() as db:
        manager.load(db)
        manager.set(db, "max_positions", "11", changed_by="test")

        assert manager.get("max_positions") == "11"
        history = db.scalars(select(ConfigHistory).where(ConfigHistory.key == "max_positions")).all()
        assert len(history) == 1
        assert history[0].old_value == "10"
        assert history[0].new_value == "11"


def test_set_invalid_value_raises():
    manager = reset_manager()
    with build_session() as db:
        manager.load(db)
        try:
            manager.set(db, "max_positions", "300", changed_by="test")
            raised = False
        except ValueError:
            raised = True

        assert raised is True
