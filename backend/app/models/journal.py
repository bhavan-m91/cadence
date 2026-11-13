import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUID_PK, Base, TimestampMixin, UserOwnedMixin
from app.models.enums import EntryStatus, InputMethod, pg_enum


class JournalEntry(Base, UserOwnedMixin, TimestampMixin):
    __tablename__ = "journal_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    entry_date: Mapped[date] = mapped_column(Date)
    covers_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    covers_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    raw_text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64))
    title: Mapped[str | None] = mapped_column(String(120))
    input_method: Mapped[InputMethod] = mapped_column(pg_enum(InputMethod, "input_method"), server_default="typed")
    dictation_seconds: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[EntryStatus] = mapped_column(pg_enum(EntryStatus, "entry_status"), server_default="draft")
    latest_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JournalEntryRevision(Base, UserOwnedMixin):
    __tablename__ = "journal_entry_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"))
    revision: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str] = mapped_column(Text)
    covers_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    covers_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
