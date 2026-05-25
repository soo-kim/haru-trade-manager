from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ConfigManager
from app.db.models.config import Config, ConfigHistory


class ConfigRepository:
    def __init__(self, manager: ConfigManager) -> None:
        self.manager = manager

    def load_into_manager(self, db: Session) -> None:
        rows = db.scalars(select(Config)).all()
        for row in rows:
            try:
                self.manager.set(row.key, row.value, allow_read_only=True)
            except KeyError:
                # 제거된 레거시 설정 키는 로드 단계에서 무시한다.
                continue

    def set(self, db: Session, key: str, value: str, changed_by: str = "system") -> None:
        old_value = None
        row = db.get(Config, key)
        if row is None:
            row = Config(key=key, value=value)
            db.add(row)
        else:
            old_value = row.value
            row.value = value

        self.manager.set(key, value)
        db.add(ConfigHistory(key=key, old_value=old_value, new_value=value, changed_by=changed_by))
        db.commit()

    def get(self, key: str) -> str:
        return self.manager.get(key)

    def list_history(
        self,
        db: Session,
        *,
        key: str | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ConfigHistory]:
        stmt = select(ConfigHistory)
        if key is not None and key.strip():
            stmt = stmt.where(ConfigHistory.key == key)
        rows = db.scalars(
            stmt.order_by(ConfigHistory.changed_at.desc()).offset(max(offset, 0)).limit(limit)
        ).all()
        return list(rows)

    def count_history(self, db: Session, *, key: str | None = None) -> int:
        stmt = select(ConfigHistory.id)
        if key is not None and key.strip():
            stmt = stmt.where(ConfigHistory.key == key)
        return len(db.scalars(stmt).all())
