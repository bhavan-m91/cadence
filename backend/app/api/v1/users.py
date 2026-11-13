from fastapi import APIRouter, BackgroundTasks, Query, status
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser
from app.core.database import get_session_factory
from app.schemas.auth import AuthEventOut, DeleteAccountIn, UserOut
from app.schemas.common import Envelope, ok
from app.schemas.user import (
    ExportOut,
    OnboardingIn,
    OnboardingOut,
    PreferencesOut,
    PreferencesPatch,
    ProfilePatch,
)
from app.services import email_service, export_service
from app.services.auth_service import AuthService
from app.services.onboarding_service import OnboardingService
from app.services.user_service import UserService, user_out

router = APIRouter(prefix="/users/me", tags=["users"])


@router.get("", response_model=Envelope[UserOut])
async def me(user: CurrentUser):
    return ok(user_out(user))


@router.patch("", response_model=Envelope[UserOut])
async def update_me(body: ProfilePatch, user: CurrentUser, session: DB):
    return ok(user_out(await UserService(session, user).update_profile(body)))


@router.delete("", status_code=204)
async def delete_me(body: DeleteAccountIn, user: CurrentUser, session: DB, bg: BackgroundTasks):
    email = user.email
    await AuthService(session).delete_account(user, body.password, body.confirm)
    bg.add_task(email_service.send, email_service.deletion_email(email))
    return Response(status_code=204)


@router.get("/preferences", response_model=Envelope[PreferencesOut])
async def get_preferences(user: CurrentUser, session: DB):
    return ok(await UserService(session, user).preferences())


@router.patch("/preferences", response_model=Envelope[PreferencesOut])
async def update_preferences(body: PreferencesPatch, user: CurrentUser, session: DB):
    return ok(await UserService(session, user).update_preferences(body))


@router.get("/auth-events", response_model=Envelope[list[AuthEventOut]])
async def auth_events(user: CurrentUser, session: DB, limit: int = Query(20, ge=1, le=100)):
    return ok(await UserService(session, user).auth_events(limit))


@router.post("/onboarding", response_model=Envelope[OnboardingOut])
async def onboarding(body: OnboardingIn, user: CurrentUser, session: DB):
    return ok(await OnboardingService(session, user).run(body))


async def _run_export_in_new_session(job_id) -> None:
    async with get_session_factory()() as s:
        await export_service.run_export(s, job_id)


@router.post("/exports", response_model=Envelope[ExportOut], status_code=status.HTTP_202_ACCEPTED)
async def request_export(user: CurrentUser, session: DB, bg: BackgroundTasks):
    from app.core.errors import RateLimited
    from app.core.rate_limit import limiter

    if limiter.hit(f"export:{user.id}", 3600) > 3:
        raise RateLimited(limiter.retry_after(f"export:{user.id}", 3600))
    job = await export_service.request_export(session, user)
    bg.add_task(_run_export_in_new_session, job.id)
    return ok(ExportOut(id=job.id, status=job.status))
