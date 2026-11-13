"""Registration, sessions, Google sign-in, verification, reset and deletion (FR-001..FR-012, D-19)."""

import uuid
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, Conflict, RateLimited, Unauthenticated, ValidationFailed
from app.core.rate_limit import limiter
from app.core.security import (
    DUMMY_HASH,
    create_access_token,
    create_state_token,
    decode_state_token,
    hash_password,
    hash_token,
    new_opaque_token,
    validate_password_strength,
    verify_password,
)
from app.core.time import get_zone
from app.models import EmailToken, RefreshToken, User, UserPreferences
from app.models.enums import AuthEventType, EmailTokenPurpose
from app.repositories.users import UsersRepository
from app.services.category_service import ensure_roots

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

# Deleted in dependency order; RESTRICT foreign keys make a single cascading delete order-sensitive.
USER_DATA_DELETES = [
    "activity_events", "activity_day_slices", "activity_tags", "activities", "ideal_allocations", "ideal_templates",
    "keyword_rules", "tag_aliases", "tags", "tasks", "projects", "export_jobs", "idempotency_keys",
]


class SessionTokens:
    def __init__(self, access_token: str, expires_in: int, refresh_token: str, persistent: bool):
        self.access_token, self.expires_in, self.refresh_token, self.persistent = access_token, expires_in, refresh_token, persistent


async def fetch_google_profile(code: str) -> dict:
    """Exchange the authorization code and read the OIDC userinfo. Isolated so tests can replace it."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=10) as client:
        tok = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
            "redirect_uri": f"{s.api_base_url}/api/v1/auth/google/callback", "grant_type": "authorization_code"})
        tok.raise_for_status()
        info = await client.get(GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
        info.raise_for_status()
        return info.json()


def safe_redirect(path: str | None) -> str:
    return path if path and path.startswith("/") and not path.startswith("//") else "/"


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UsersRepository(session)

    # ---------------------------------------------------------------- sessions
    async def _issue_session(self, user: User, persistent: bool, ip: str | None, ua: str | None, family_id: uuid.UUID | None = None) -> SessionTokens:
        s = get_settings()
        raw, hashed = new_opaque_token()
        ttl = timedelta(days=s.refresh_ttl_days) if persistent else timedelta(hours=s.session_refresh_ttl_hours)
        self.session.add(RefreshToken(user_id=user.id, family_id=family_id or uuid.uuid4(), token_hash=hashed,
                                      expires_at=datetime.now(UTC) + ttl, user_agent=(ua or "")[:200] or None, ip=ip))
        access, expires_in = create_access_token(user.id)
        return SessionTokens(access, expires_in, raw, persistent)

    async def register(self, email: str, password: str, display_name: str, timezone: str, ip: str | None, ua: str | None) -> tuple[User, SessionTokens, str]:
        get_zone(timezone)
        validate_password_strength(password)
        if await self.users.get_by_email(email):
            raise Conflict("An account with that email already exists", code="EMAIL_TAKEN")
        user = User(email=email, password_hash=hash_password(password), display_name=display_name, timezone=timezone)
        self.session.add(user)
        try:
            await self.session.flush()
        except IntegrityError as e:  # lost a race on the unique email
            await self.session.rollback()
            raise Conflict("An account with that email already exists", code="EMAIL_TAKEN") from e
        self.session.add(UserPreferences(user_id=user.id))
        await ensure_roots(self.session, user.id)
        verify_raw = await self._new_email_token(user, EmailTokenPurpose.verify_email, timedelta(hours=24))
        tokens = await self._issue_session(user, True, ip, ua)
        await self.session.commit()
        await self.session.refresh(user)
        return user, tokens, verify_raw

    async def login(self, email: str, password: str, remember: bool, ip: str | None, ua: str | None) -> tuple[User, SessionTokens]:
        s = get_settings()
        key = f"login:{email.lower()}|{ip}"
        if limiter.count(key, s.login_window_seconds) >= s.login_max_failures:
            raise RateLimited(limiter.retry_after(key, s.login_window_seconds), "Too many sign-in attempts. Try again later.")
        user = await self.users.get_by_email(email)
        valid = verify_password(password, user.password_hash if user else DUMMY_HASH) and user is not None and user.password_hash is not None
        if not valid:
            limiter.hit(key, s.login_window_seconds)
            self.users.add_auth_event(user.id if user else None, AuthEventType.login_fail, ip, ua)
            await self.session.commit()
            raise Unauthenticated("Email or password is incorrect", code="INVALID_CREDENTIALS")
        self.users.add_auth_event(user.id, AuthEventType.login_ok, ip, ua)
        tokens = await self._issue_session(user, remember, ip, ua)
        await self.session.commit()
        return user, tokens

    async def refresh(self, raw: str | None, ip: str | None, ua: str | None) -> tuple[User, SessionTokens]:
        if not raw:
            raise Unauthenticated("No session", code="INVALID_TOKEN")
        row = await self.users.token_by_hash(hash_token(raw))
        now = datetime.now(UTC)
        if row is None or row.revoked_at is not None or row.expires_at <= now:
            raise Unauthenticated("Session expired", code="INVALID_TOKEN")
        if row.rotated_at is not None:
            await self.users.revoke_family(row.family_id)  # reuse of a rotated token: kill the whole family (FR-006)
            await self.session.commit()
            raise Unauthenticated("Session expired", code="INVALID_TOKEN")
        user = await self.users.get(row.user_id)
        if user is None:
            raise Unauthenticated("Session expired", code="INVALID_TOKEN")
        persistent = (row.expires_at - row.created_at) > timedelta(days=2)
        row.rotated_at = now
        tokens = await self._issue_session(user, persistent, ip, ua, row.family_id)
        await self.session.commit()
        return user, tokens

    async def logout(self, raw: str | None, everywhere: bool, ip: str | None, ua: str | None) -> None:
        if not raw:
            return
        row = await self.users.token_by_hash(hash_token(raw))
        if row is None:
            return
        if everywhere:
            await self.users.revoke_all_for_user(row.user_id)
        else:
            await self.users.revoke_family(row.family_id)
        self.users.add_auth_event(row.user_id, AuthEventType.logout, ip, ua)
        await self.session.commit()

    # ---------------------------------------------------------------- google
    def google_start(self, redirect: str | None) -> str:
        s = get_settings()
        if not s.google_client_id:
            raise AppError("Google sign-in is not configured", code="OAUTH_NOT_CONFIGURED", status=501)
        state = create_state_token({"redirect": safe_redirect(redirect), "n": uuid.uuid4().hex})
        return GOOGLE_AUTH_URL + "?" + urlencode({
            "client_id": s.google_client_id, "redirect_uri": f"{s.api_base_url}/api/v1/auth/google/callback",
            "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"})

    async def google_callback(self, code: str, state: str, ip: str | None, ua: str | None) -> tuple[User, SessionTokens, str]:
        payload = decode_state_token(state)
        try:
            profile = await fetch_google_profile(code)
        except Exception as e:  # noqa: BLE001
            raise AppError("Google sign-in failed", code="OAUTH_FAILED", status=400) from e
        sub, email = profile.get("sub"), (profile.get("email") or "").lower()
        verified = bool(profile.get("email_verified"))
        if not sub or not email:
            raise AppError("Google sign-in failed", code="OAUTH_FAILED", status=400)

        user = await self.users.get_by_google_sub(sub)
        if user is None:
            existing = await self.users.get_by_email(email)
            if existing is not None:
                if not verified:  # AC-006: never link on an unverified email
                    raise AppError("Google did not verify that email address", code="OAUTH_FAILED", status=400)
                existing.google_sub = sub
                existing.email_verified_at = existing.email_verified_at or datetime.now(UTC)
                self.users.add_auth_event(existing.id, AuthEventType.google_linked, ip, ua)
                user = existing
            else:
                user = User(email=email, google_sub=sub, display_name=(profile.get("name") or email.split("@")[0])[:80],
                            email_verified_at=datetime.now(UTC) if verified else None)
                self.session.add(user)
                await self.session.flush()
                self.session.add(UserPreferences(user_id=user.id))
                await ensure_roots(self.session, user.id)
        self.users.add_auth_event(user.id, AuthEventType.login_ok, ip, ua)
        tokens = await self._issue_session(user, True, ip, ua)
        await self.session.commit()
        return user, tokens, safe_redirect(payload.get("redirect"))

    # ---------------------------------------------------------------- email tokens
    async def _new_email_token(self, user: User, purpose: EmailTokenPurpose, ttl: timedelta) -> str:
        raw, hashed = new_opaque_token()
        self.session.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=hashed, expires_at=datetime.now(UTC) + ttl))
        return raw

    async def _consume(self, raw: str, purpose: EmailTokenPurpose) -> EmailToken:
        tok = await self.users.email_token(hash_token(raw), purpose)
        if tok is None or tok.used_at is not None or tok.expires_at <= datetime.now(UTC):
            raise AppError("This link is invalid or has expired", code="INVALID_TOKEN", status=400)
        tok.used_at = datetime.now(UTC)
        return tok

    async def verify_email(self, raw: str) -> None:
        tok = await self._consume(raw, EmailTokenPurpose.verify_email)
        user = await self.users.get(tok.user_id)
        if user is not None and user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
        await self.session.commit()

    async def resend_verification(self, user: User) -> str | None:
        if user.email_verified_at is not None:
            return None
        raw = await self._new_email_token(user, EmailTokenPurpose.verify_email, timedelta(hours=24))
        await self.session.commit()
        return raw

    async def forgot_password(self, email: str, ip: str | None, ua: str | None) -> tuple[User, str] | None:
        key = f"forgot:{ip}"
        if limiter.hit(key, 3600) > 5:
            raise RateLimited(limiter.retry_after(key, 3600))
        user = await self.users.get_by_email(email)
        if user is None:
            return None
        raw = await self._new_email_token(user, EmailTokenPurpose.reset_password, timedelta(hours=1))
        self.users.add_auth_event(user.id, AuthEventType.reset_requested, ip, ua)
        await self.session.commit()
        return user, raw

    async def reset_password(self, raw: str, password: str, ip: str | None, ua: str | None) -> None:
        validate_password_strength(password)
        tok = await self._consume(raw, EmailTokenPurpose.reset_password)
        user = await self.users.get(tok.user_id)
        user.password_hash = hash_password(password)
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)  # they proved control of the mailbox
        await self.users.revoke_all_for_user(user.id)  # FR-008
        self.users.add_auth_event(user.id, AuthEventType.reset_done, ip, ua)
        await self.session.commit()

    async def change_password(self, user: User, current: str, new: str, ip: str | None, ua: str | None) -> None:
        if user.password_hash is None:
            raise AppError("This account has no password yet. Use 'Forgot password' to set one.", code="NO_PASSWORD_SET", status=400)
        if not verify_password(current, user.password_hash):
            raise Unauthenticated("Current password is incorrect", code="INVALID_CREDENTIALS")
        validate_password_strength(new)
        user.password_hash = hash_password(new)
        await self.users.revoke_all_for_user(user.id)
        self.users.add_auth_event(user.id, AuthEventType.password_changed, ip, ua)
        await self.session.commit()

    # ---------------------------------------------------------------- deletion
    async def delete_account(self, user: User, password: str | None, confirm: str) -> None:
        if confirm != "DELETE":
            raise ValidationFailed("Type DELETE to confirm", path="confirm", rule="confirm_mismatch")
        if user.email_verified_at is None:
            raise AppError("Verify your email before deleting your account", code="EMAIL_NOT_VERIFIED", status=403)
        if user.password_hash is None:
            raise Unauthenticated("Set a password first (use 'Forgot password'), then delete", code="REAUTH_REQUIRED")
        if not password or not verify_password(password, user.password_hash):
            raise Unauthenticated("Password is incorrect", code="INVALID_CREDENTIALS")
        uid = user.id
        for table in USER_DATA_DELETES[:4]:
            await self.session.execute(text(f"DELETE FROM {table} WHERE user_id = :u"), {"u": uid})
        await self.session.execute(text("UPDATE journal_entries SET latest_job_id = NULL WHERE user_id = :u"), {"u": uid})
        await self.session.execute(text("DELETE FROM ai_processing_jobs WHERE user_id = :u"), {"u": uid})
        await self.session.execute(text("DELETE FROM journal_entries WHERE user_id = :u"), {"u": uid})
        for table in USER_DATA_DELETES[4:]:
            await self.session.execute(text(f"DELETE FROM {table} WHERE user_id = :u"), {"u": uid})
        await self.session.execute(text("DELETE FROM categories WHERE user_id = :u"), {"u": uid})
        await self.session.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
        await self.session.commit()
