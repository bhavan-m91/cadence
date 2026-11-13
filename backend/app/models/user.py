import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUID_PK, Base, TimestampMixin
from app.models.enums import (
    AuthEventType,
    CoveragePreset,
    EmailTokenPurpose,
    Theme,
    TimeFormat,
    TranscriptionMode,
    pg_enum,
)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    password_hash: Mapped[str | None] = mapped_column(Text)
    google_sub: Mapped[str | None] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(String(80))
    role_title: Mapped[str | None] = mapped_column(String(80))
    timezone: Mapped[str] = mapped_column(String(64), server_default="Asia/Kolkata")
    theme: Mapped[Theme] = mapped_column(pg_enum(Theme, "theme_pref"), server_default="system")
    data_revision: Mapped[int] = mapped_column(BigInteger, server_default="0")
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    week_start: Mapped[int] = mapped_column(SmallInteger, server_default="1")
    time_format: Mapped[TimeFormat] = mapped_column(pg_enum(TimeFormat, "time_format"), server_default="12h")
    coverage_tolerance_minutes: Mapped[int] = mapped_column(SmallInteger, server_default="10")
    gap_min_minutes: Mapped[int] = mapped_column(SmallInteger, server_default="10")
    short_night_minutes: Mapped[int] = mapped_column(SmallInteger, server_default="420")
    office_start_minute: Mapped[int] = mapped_column(SmallInteger, server_default="540")
    office_end_minute: Mapped[int] = mapped_column(SmallInteger, server_default="1080")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    default_coverage_preset: Mapped[CoveragePreset] = mapped_column(
        pg_enum(CoveragePreset, "coverage_preset"), server_default="whole_day"
    )
    transcription_mode: Mapped[TranscriptionMode] = mapped_column(
        pg_enum(TranscriptionMode, "transcription_mode"), server_default="auto"
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    ip: Mapped[str | None] = mapped_column(INET)


class EmailToken(Base):
    __tablename__ = "email_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[EmailTokenPurpose] = mapped_column(pg_enum(EmailTokenPurpose, "email_token_purpose"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthEvent(Base):
    __tablename__ = "auth_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    event_type: Mapped[AuthEventType] = mapped_column(pg_enum(AuthEventType, "auth_event_type"))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


__all__ = ["User", "UserPreferences", "RefreshToken", "EmailToken", "AuthEvent", "Integer"]
