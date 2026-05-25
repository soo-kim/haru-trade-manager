from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routers.config import router as config_router
from app.api.routers.backtest import router as backtest_router
from app.api.routers.health import router as health_router
from app.api.routers.system import router as system_router
from app.api.routers.telegram import router as telegram_router
from app.api.routers.trading import router as trading_router
from app.api.routers.universe import router as universe_router
from app.core.config_manager import ConfigManager
from app.core.logging import configure_logging
from app.core.settings import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.runtime.runner import RuntimeRunner
import app.db.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO")
    Base.metadata.create_all(bind=engine)
    manager = ConfigManager.get_instance()
    with SessionLocal() as db:
        manager.load(db)

    runtime: RuntimeRunner | None = None
    if settings.enable_background_loops:
        runtime = RuntimeRunner(manager)
        runtime.start()
    app.state.runtime = runtime

    yield
    if runtime is not None:
        await runtime.stop()


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(health_router)
app.include_router(config_router)
app.include_router(system_router)
app.include_router(telegram_router)
app.include_router(trading_router)
app.include_router(backtest_router)
app.include_router(universe_router)
