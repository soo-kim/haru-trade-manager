from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request as FastAPIRequest, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel


class OtpVerifyRequest(BaseModel):
    code: str


def _client_ip(request: FastAPIRequest) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate
    if request.client is not None and request.client.host:
        return request.client.host
    return "알수없음"


def create_auth_router(
    *,
    auth_service,
    load_dashboard_html: Callable[[str], str],
    session_cookie_name: str,
) -> APIRouter:
    router = APIRouter()

    @router.post("/auth/otp/request")
    async def request_otp(request: FastAPIRequest) -> dict[str, object]:
        ip = _client_ip(request)
        return await auth_service.request_otp(ip=ip)

    @router.post("/auth/otp/verify")
    async def verify_otp(req: OtpVerifyRequest, request: FastAPIRequest, response: Response) -> dict[str, object]:
        ip = _client_ip(request)
        result = await auth_service.verify_otp(ip=ip, code=req.code)
        if result.get("ok"):
            response.set_cookie(
                key=session_cookie_name,
                value=str(result["session_id"]),
                httponly=True,
                secure=False,
                samesite="lax",
                max_age=int(result["expires_in_seconds"]),
            )
        return result

    @router.get("/auth/session")
    def auth_session(request: FastAPIRequest) -> dict[str, object]:
        session_id = request.cookies.get(session_cookie_name)
        if session_id is None:
            return {"ok": False, "error": "session_missing"}
        return auth_service.validate_session(session_id=session_id, ip=_client_ip(request))

    @router.post("/auth/logout")
    def auth_logout(request: FastAPIRequest, response: Response) -> dict[str, object]:
        session_id = request.cookies.get(session_cookie_name)
        if session_id is not None:
            auth_service.revoke_session(session_id)
        response.delete_cookie(session_cookie_name)
        return {"ok": True}

    @router.get("/dashboard/login", response_class=HTMLResponse)
    def dashboard_login_page() -> HTMLResponse:
        return HTMLResponse(load_dashboard_html("dashboard_login.html"))

    @router.get("/dashboard/app", response_class=HTMLResponse)
    def dashboard_app_page(request: FastAPIRequest) -> HTMLResponse:
        session_id = request.cookies.get(session_cookie_name)
        if session_id is None:
            return RedirectResponse(url="/dashboard/login", status_code=302)
        valid = auth_service.validate_session(session_id=session_id, ip=_client_ip(request))
        if not valid.get("ok"):
            return RedirectResponse(url="/dashboard/login", status_code=302)
        return HTMLResponse(load_dashboard_html("dashboard_app.html"))

    return router
