from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import ConfigManager
from app.repositories.config import ConfigRepository


SessionFactory = Callable[[], Session]
ConfigChangeHook = Callable[[str, str, str], None]


class ConfigService:
    def __init__(
        self,
        manager: ConfigManager,
        *,
        session_factory: SessionFactory | None = None,
        on_change: ConfigChangeHook | None = None,
    ) -> None:
        self.manager = manager
        self.repo = ConfigRepository(manager)
        self.session_factory = session_factory
        self.on_change = on_change

    def load_from_db(self) -> None:
        if self.session_factory is None:
            return
        try:
            with self.session_factory() as db:
                self.repo.load_into_manager(db)
        except SQLAlchemyError:
            # DB가 일시적으로 불가능해도 앱은 축소 모드로 기동해야 한다.
            return

    def get_all(self) -> dict[str, str]:
        return self.manager.get_all()

    def describe(self, key: str) -> dict[str, object]:
        return self.manager.describe(key)

    def set(self, *, key: str, value: str, changed_by: str = "system") -> None:
        if self.session_factory is None:
            self.manager.set(key, value)
            self._run_on_change(key=key, value=value, changed_by=changed_by)
            return

        try:
            with self.session_factory() as db:
                self.repo.set(db, key, value, changed_by=changed_by)
        except SQLAlchemyError:
            self.manager.set(key, value)
        self._run_on_change(key=key, value=value, changed_by=changed_by)

    def _run_on_change(self, *, key: str, value: str, changed_by: str) -> None:
        if self.on_change is None:
            return
        try:
            self.on_change(key, value, changed_by)
        except Exception:  # noqa: BLE001
            # 설정 반영 자체는 유지하고, 후처리 실패는 런타임에서 복구 가능해야 한다.
            return
