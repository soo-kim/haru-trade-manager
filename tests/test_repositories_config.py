from sqlalchemy import select

from app.core.config import ConfigManager
from app.db.models.config import ConfigHistory
from app.repositories.config import ConfigRepository
from tests.utils import build_session


def test_config_repository_set_and_history():
    manager = ConfigManager(initial={"max_positions": "10", "daily_base_capital": "10000000"})
    repo = ConfigRepository(manager)
    with build_session() as db:
        repo.set(db, "max_positions", "12", changed_by="test")
        assert repo.get("max_positions") == "12"
        hist = db.scalars(select(ConfigHistory).where(ConfigHistory.key == "max_positions")).all()
        assert len(hist) == 1
        assert hist[0].new_value == "12"


def test_config_repository_history_list_and_count():
    manager = ConfigManager(initial={"max_positions": "10", "daily_base_capital": "10000000"})
    repo = ConfigRepository(manager)
    with build_session() as db:
        repo.set(db, "max_positions", "11", changed_by="a")
        repo.set(db, "max_positions", "12", changed_by="b")
        repo.set(db, "liquidity_threshold", "55", changed_by="c")

        rows = repo.list_history(db, key="max_positions", offset=0, limit=10)
        assert len(rows) == 2
        assert repo.count_history(db, key="max_positions") == 2
        assert repo.count_history(db) == 3
