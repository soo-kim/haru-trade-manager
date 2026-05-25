from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.command_service import CommandService

router = APIRouter(prefix="/telegram", tags=["telegram"])


class CommandRequest(BaseModel):
    command: str


@router.post("/command")
def telegram_command(request: CommandRequest, app_request: Request) -> dict[str, str]:
    runtime = getattr(app_request.app.state, "runtime", None)
    service = CommandService(runtime)
    result = service.execute(request.command)
    return {"result": result}
