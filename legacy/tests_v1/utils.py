from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config_manager import ConfigManager
from app.core.settings import settings
from app.db.base import Base
import app.db.models  # noqa: F401


def build_session() -> Session:
    engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    maker = sessionmaker(bind=engine, class_=Session, autocommit=False, autoflush=False)
    return maker()


def reset_manager() -> ConfigManager:
    ConfigManager._instance = None  # type: ignore[attr-defined]
    return ConfigManager.get_instance()
