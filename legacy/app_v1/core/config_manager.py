from __future__ import annotations

from threading import Lock

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config_schema import DEFAULT_CONFIGS, validate_config_value
from app.db.models.config import Config, ConfigHistory


class ConfigManager:
    _instance: ConfigManager | None = None
    _instance_lock = Lock()

    def __init__(self) -> None:
        self._lock = Lock()
        self._cache: dict[str, str] = {}

    @classmethod
    def get_instance(cls) -> ConfigManager:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = ConfigManager()
        return cls._instance

    def load(self, db: Session) -> None:
        with self._lock:
            rows = db.scalars(select(Config)).all()
            self._cache = {row.key: row.value for row in rows}
            missing = {k: v for k, v in DEFAULT_CONFIGS.items() if k not in self._cache}
            if missing:
                for key, value in missing.items():
                    db.add(Config(key=key, value=value))
                db.commit()
                self._cache.update(missing)

    def get(self, key: str) -> str:
        with self._lock:
            if key not in self._cache:
                raise KeyError(f"Unknown config key: {key}")
            return self._cache[key]

    def get_all(self) -> dict[str, str]:
        with self._lock:
            return dict(self._cache)

    def set(self, db: Session, key: str, value: str, changed_by: str = "system") -> None:
        validate_config_value(key, value)

        with self._lock:
            old_value = self._cache.get(key)

            row = db.get(Config, key)
            if row is None:
                row = Config(key=key, value=value)
                db.add(row)
            else:
                row.value = value

            history = ConfigHistory(
                key=key,
                old_value=old_value,
                new_value=value,
                changed_by=changed_by,
            )
            db.add(history)
            db.commit()

            self._cache[key] = value
