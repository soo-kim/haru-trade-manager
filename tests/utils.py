from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import settings
from app.db.base import Base
import app.db.models  # noqa: F401


def _create_temp_schema(base_engine) -> str:
    schema = f"test_{uuid4().hex}"
    with base_engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    return schema


def build_session_factory():
    """
    테스트 전용 세션 팩토리.
    각 팩토리마다 고유 스키마를 만들고, 해당 스키마에만 테이블을 생성한다.
    """
    base_engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    schema = _create_temp_schema(base_engine)
    scoped_engine = base_engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(bind=scoped_engine)
    return sessionmaker(bind=scoped_engine, class_=Session, autocommit=False, autoflush=False)


@contextmanager
def build_session() -> Iterator[Session]:
    """
    테스트 전용 세션 빌더.
    PostgreSQL 테스트 DB에 임시 스키마를 생성해 테스트 간 격리를 보장한다.
    """
    base_engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    schema = _create_temp_schema(base_engine)
    scoped_engine = base_engine.execution_options(schema_translate_map={None: schema})
    Base.metadata.create_all(bind=scoped_engine)
    factory = sessionmaker(bind=scoped_engine, class_=Session, autocommit=False, autoflush=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        with base_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        base_engine.dispose()
