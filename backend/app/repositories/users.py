import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthEvent, EmailToken, RefreshToken, User, UserPreferences
from app.models.enums import AuthEventType, EmailTokenPurpose


class UsersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        return (await self.session.execute(select(User).where(User.email == email))).scalar_one_or_none()

    async def get_by_google_sub(self, sub: str) -> User | None:
        return (await self.session.execute(select(User).where(User.google_sub == sub))).scalar_one_or_none()

    async def preferences(self, user_id: uuid.UUID) -> UserPreferences:
        prefs = await self.session.get(UserPreferences, user_id)
        if prefs is None:
            prefs = UserPreferences(user_id=user_id)
            self.session.add(prefs)
            await self.session.flush()
            await self.session.refresh(prefs)
        return prefs

    async def bump_revision(self, user_id: uuid.UUID) -> None:
        await self.session.execute(update(User).where(User.id == user_id).values(data_revision=User.data_revision + 1))

    # refresh tokens
    async def token_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def revoke_family(self, family_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

    async def purge_expired_tokens(self) -> None:
        await self.session.execute(delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(UTC)))

    # email tokens
    async def email_token(self, token_hash: str, purpose: EmailTokenPurpose) -> EmailToken | None:
        stmt = (
            select(EmailToken)
            .where(EmailToken.token_hash == token_hash, EmailToken.purpose == purpose)
            .with_for_update()
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    # events
    def add_auth_event(self, user_id: uuid.UUID | None, event: AuthEventType, ip: str | None, ua: str | None) -> None:
        self.session.add(AuthEvent(user_id=user_id, event_type=event, ip=ip, user_agent=(ua or "")[:200] or None))

    async def recent_auth_events(self, user_id: uuid.UUID, limit: int) -> list[AuthEvent]:
        stmt = select(AuthEvent).where(AuthEvent.user_id == user_id).order_by(AuthEvent.created_at.desc(), AuthEvent.id.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars())

    async def count_users(self) -> int:
        return (await self.session.execute(select(func.count()).select_from(User))).scalar_one()
