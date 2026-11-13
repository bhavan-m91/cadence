"""Security primitives: argon2id hashing, JWT access tokens, opaque refresh/email tokens (D-19)."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.common_passwords import COMMON_PASSWORDS
from app.core.config import get_settings
from app.core.errors import AppError, Unauthenticated

_hasher = PasswordHasher()
MIN_PASSWORD_LENGTH = 10


def validate_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AppError(
            f"Use at least {MIN_PASSWORD_LENGTH} characters", code="WEAK_PASSWORD", status=422,
            details={"fields": [{"path": "password", "rule": "min_length", "message": f"Use at least {MIN_PASSWORD_LENGTH} characters"}]},
        )
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 4:
        raise AppError(
            "That password is too common", code="WEAK_PASSWORD", status=422,
            details={"fields": [{"path": "password", "rule": "common_password", "message": "That password is too common"}]},
        )


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Used to keep login timing similar for unknown emails.
DUMMY_HASH = _hasher.hash("not-a-real-password")


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=s.access_ttl_minutes)
    token = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": exp, "jti": uuid.uuid4().hex}, s.jwt_secret, algorithm=s.jwt_algorithm
    )
    return token, s.access_ttl_minutes * 60


def decode_access_token(token: str) -> uuid.UUID:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm], leeway=30, options={"require": ["exp", "sub"]})
        return uuid.UUID(payload["sub"])
    except jwt.ExpiredSignatureError as e:
        raise Unauthenticated("Token expired", code="TOKEN_EXPIRED") from e
    except (jwt.PyJWTError, ValueError) as e:
        raise Unauthenticated("Invalid token") from e


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_opaque_token() -> tuple[str, str]:
    """Returns (raw, sha256-hex). Only the hash is stored (FR-005)."""
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def create_state_token(payload: dict, ttl_seconds: int = 600) -> str:
    s = get_settings()
    now = datetime.now(UTC)
    return jwt.encode({**payload, "iat": now, "exp": now + timedelta(seconds=ttl_seconds)}, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_state_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as e:
        raise AppError("Sign-in could not be completed", code="OAUTH_FAILED", status=400) from e
