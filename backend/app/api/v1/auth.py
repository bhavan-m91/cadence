from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Cookie, Query, Request, Response
from fastapi.responses import RedirectResponse

from app.api.deps import DB, CurrentUser, client_ip, user_agent
from app.core.config import get_settings
from app.schemas.auth import (
    AuthOut,
    ChangePasswordIn,
    ForgotIn,
    LoginIn,
    LogoutIn,
    RefreshOut,
    RegisterIn,
    ResetIn,
    TokenIn,
)
from app.schemas.common import Envelope, OkOut, ok
from app.services import email_service
from app.services.auth_service import AuthService, SessionTokens
from app.services.user_service import user_out

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE_PATH = "/api/v1/auth"


def set_refresh_cookie(response: Response, tokens: SessionTokens) -> None:
    s = get_settings()
    response.set_cookie(
        s.refresh_cookie_name, tokens.refresh_token, max_age=s.refresh_ttl_days * 86400 if tokens.persistent else None,
        httponly=True, secure=s.cookie_secure, samesite=s.cookie_samesite, path=COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.refresh_cookie_name, path=COOKIE_PATH, httponly=True, secure=s.cookie_secure, samesite=s.cookie_samesite)


RefreshCookie = Annotated[str | None, Cookie(alias="refresh_token")]


@router.post("/register", response_model=Envelope[AuthOut], status_code=201)
async def register(body: RegisterIn, request: Request, response: Response, session: DB, bg: BackgroundTasks):
    user, tokens, verify_raw = await AuthService(session).register(
        body.email, body.password, body.display_name, body.timezone, client_ip(request), user_agent(request))
    bg.add_task(email_service.send, email_service.verification_email(user.email, verify_raw))
    set_refresh_cookie(response, tokens)
    return ok({"access_token": tokens.access_token, "expires_in": tokens.expires_in, "user": user_out(user)})


@router.post("/login", response_model=Envelope[AuthOut])
async def login(body: LoginIn, request: Request, response: Response, session: DB):
    user, tokens = await AuthService(session).login(body.email, body.password, body.remember, client_ip(request), user_agent(request))
    set_refresh_cookie(response, tokens)
    return ok({"access_token": tokens.access_token, "expires_in": tokens.expires_in, "user": user_out(user)})


@router.post("/refresh", response_model=Envelope[RefreshOut])
async def refresh(request: Request, response: Response, session: DB, refresh_token: RefreshCookie = None):
    try:
        _, tokens = await AuthService(session).refresh(refresh_token, client_ip(request), user_agent(request))
    except Exception:
        clear_refresh_cookie(response)
        raise
    set_refresh_cookie(response, tokens)
    return ok({"access_token": tokens.access_token, "expires_in": tokens.expires_in})


@router.post("/logout", response_model=Envelope[OkOut])
async def logout(request: Request, response: Response, session: DB, body: LogoutIn | None = None, refresh_token: RefreshCookie = None):
    await AuthService(session).logout(refresh_token, bool(body and body.all), client_ip(request), user_agent(request))
    clear_refresh_cookie(response)
    return ok({"ok": True})


@router.get("/google/start", status_code=302)
async def google_start(session: DB, redirect: Annotated[str | None, Query(max_length=200)] = None):
    return RedirectResponse(AuthService(session).google_start(redirect), status_code=302)


@router.get("/google/callback", status_code=302)
async def google_callback(request: Request, session: DB, code: str, state: str):
    _, tokens, redirect = await AuthService(session).google_callback(code, state, client_ip(request), user_agent(request))
    response = RedirectResponse(f"{get_settings().app_base_url}{redirect}", status_code=302)
    set_refresh_cookie(response, tokens)
    return response


@router.post("/verify-email", response_model=Envelope[OkOut])
async def verify_email(body: TokenIn, session: DB):
    await AuthService(session).verify_email(body.token)
    return ok({"ok": True})


@router.post("/resend-verification", response_model=Envelope[OkOut])
async def resend_verification(user: CurrentUser, session: DB, bg: BackgroundTasks):
    raw = await AuthService(session).resend_verification(user)
    if raw:
        bg.add_task(email_service.send, email_service.verification_email(user.email, raw))
    return ok({"ok": True})


@router.post("/password/forgot", response_model=Envelope[OkOut])
async def forgot_password(body: ForgotIn, request: Request, session: DB, bg: BackgroundTasks):
    result = await AuthService(session).forgot_password(body.email, client_ip(request), user_agent(request))
    if result:  # identical response for known and unknown emails (FR-007)
        user, raw = result
        bg.add_task(email_service.send, email_service.reset_email(user.email, raw))
    return ok({"ok": True})


@router.post("/password/reset", response_model=Envelope[OkOut])
async def reset_password(body: ResetIn, request: Request, session: DB):
    await AuthService(session).reset_password(body.token, body.password, client_ip(request), user_agent(request))
    return ok({"ok": True})


@router.post("/password/change", response_model=Envelope[OkOut])
async def change_password(body: ChangePasswordIn, request: Request, response: Response, user: CurrentUser, session: DB):
    svc = AuthService(session)
    await svc.change_password(user, body.current_password, body.new_password, client_ip(request), user_agent(request))
    tokens = await svc._issue_session(user, True, client_ip(request), user_agent(request))  # keep this device signed in
    await session.commit()
    set_refresh_cookie(response, tokens)
    return ok({"ok": True})
