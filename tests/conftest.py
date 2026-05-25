from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


_DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://haru:haru@localhost:6432/haru_trade_test"

# 개발자 로컬 .env 값과 분리된 테스트 환경을 강제한다.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)
os.environ["ENABLE_BACKGROUND_LOOPS"] = "false"
os.environ["ENABLE_AUTO_BACKTEST"] = "false"
os.environ["KIWOOM_APP_KEY"] = ""
os.environ["KIWOOM_APP_SECRET"] = ""
os.environ["KIWOOM_ACCOUNT_NO"] = ""
os.environ["TELEGRAM_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""


def _ensure_test_database(database_url: str) -> None:
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError(f"tests require PostgreSQL DATABASE_URL, got: {url.drivername}")
    db_name = url.database
    if not db_name:
        raise RuntimeError("tests require a database name in DATABASE_URL")

    admin_url = url.set(database="postgres")
    engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name})
            if exists:
                return
            safe_name = db_name.replace('"', '""')
            conn.execute(text(f'CREATE DATABASE "{safe_name}"'))
    finally:
        engine.dispose()


def _drop_temp_test_schemas(database_url: str) -> None:
    url = make_url(database_url)
    engine = create_engine(url, future=True, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT nspname
                    FROM pg_namespace
                    WHERE nspname LIKE 'test_%'
                    """
                )
            ).fetchall()
            for (schema_name,) in rows:
                safe_name = schema_name.replace('"', '""')
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{safe_name}" CASCADE'))
    finally:
        engine.dispose()


_ensure_test_database(os.environ["DATABASE_URL"])


def pytest_sessionstart(session) -> None:  # noqa: ANN001
    from app.db.base import Base
    from app.db.session import engine
    import app.db.models  # noqa: F401

    _drop_temp_test_schemas(os.environ["DATABASE_URL"])
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ANN001
    from app.db.base import Base
    from app.db.session import engine

    Base.metadata.drop_all(bind=engine)
    _drop_temp_test_schemas(os.environ["DATABASE_URL"])
