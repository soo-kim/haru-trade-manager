from fastapi import APIRouter, Request

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/runtime")
def runtime_status(request: Request) -> dict[str, bool | float]:
    runtime = getattr(request.app.state, "runtime", None)
    payload: dict[str, bool | float] = {
        "background_loops_enabled": runtime is not None,
        "running": runtime is not None and not runtime.state.stop_requested,
    }
    if runtime is not None:
        payload["server_time_offset_sec"] = runtime.state.server_time_offset_sec
    return payload
