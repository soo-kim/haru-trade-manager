from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import ConfigSetRequest
from app.core.config_manager import ConfigManager
from app.db.session import get_db

router = APIRouter(prefix="/config", tags=["config"])
manager = ConfigManager.get_instance()


@router.get("")
def list_config() -> dict[str, str]:
    return manager.get_all()


@router.post("")
def set_config(request: ConfigSetRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        manager.set(db, request.key, request.value, changed_by=request.changed_by)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to update config: {exc}") from exc

    return {"key": request.key, "value": request.value}
