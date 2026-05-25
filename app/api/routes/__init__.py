from app.api.routes.dashboard_actions import create_dashboard_actions_router
from app.api.routes.auth import create_auth_router
from app.api.routes.dashboard_analytics import create_dashboard_analytics_router
from app.api.routes.dashboard_read import create_dashboard_read_router
from app.api.routes.dashboard_records import create_dashboard_records_router
from app.api.routes.system_core import create_system_core_router

__all__ = [
    "create_dashboard_actions_router",
    "create_auth_router",
    "create_dashboard_analytics_router",
    "create_dashboard_read_router",
    "create_dashboard_records_router",
    "create_system_core_router",
]
