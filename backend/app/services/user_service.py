import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.time import get_zone
from app.models import User
from app.repositories.users import UsersRepository
from app.schemas.auth import UserOut
from app.schemas.user import PreferencesPatch, ProfilePatch


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name, role_title=user.role_title, timezone=user.timezone,
        theme=user.theme, email_verified=user.email_verified_at is not None,
        onboarding_completed=user.onboarding_completed_at is not None, has_password=user.password_hash is not None,
    )


class UserService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = UsersRepository(session)

    async def update_profile(self, body: ProfilePatch) -> User:
        data = body.model_dump(exclude_unset=True)
        if data.get("timezone"):
            get_zone(data["timezone"])  # a later timezone change never rewrites history (PRD 5.3)
        if "display_name" in data and data["display_name"] is None:
            raise AppError("Display name cannot be empty", code="VALIDATION_ERROR", status=422)
        for k, v in data.items():
            setattr(self.user, k, v)
        await self.session.commit()
        await self.session.refresh(self.user)
        return self.user

    async def preferences(self):
        return await self.repo.preferences(self.user.id)

    async def update_preferences(self, body: PreferencesPatch):
        prefs = await self.repo.preferences(self.user.id)
        data = body.model_dump(exclude_unset=True, exclude_none=True)
        for k, v in data.items():
            setattr(prefs, k, v)
        if prefs.office_start_minute >= prefs.office_end_minute:
            await self.session.rollback()
            raise AppError("Office start must be before office end", code="VALIDATION_ERROR", status=422)
        await self.repo.bump_revision(self.user.id)
        await self.session.commit()
        await self.session.refresh(prefs)
        return prefs

    async def auth_events(self, limit: int):
        return await self.repo.recent_auth_events(self.user.id, limit)


__all__ = ["UserService", "user_out", "uuid"]
