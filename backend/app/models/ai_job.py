import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUID_PK, Base, UserOwnedMixin
from app.models.enums import AiJobStatus, AiJobType, pg_enum


class AIProcessingJob(Base, UserOwnedMixin):
    __tablename__ = "ai_processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entries.id"))
    job_type: Mapped[AiJobType] = mapped_column(pg_enum(AiJobType, "ai_job_type"), server_default="extract_activities")
    status: Mapped[AiJobStatus] = mapped_column(pg_enum(AiJobStatus, "ai_job_status"), server_default="queued")
    attempts: Mapped[int] = mapped_column(SmallInteger, server_default="0")
    entry_revision: Mapped[int] = mapped_column(Integer)
    text_hash: Mapped[str] = mapped_column(String(64))
    user_hint: Mapped[str | None] = mapped_column(String(500))
    prompt_version: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    parsed_response: Mapped[dict | None] = mapped_column(JSONB)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(40))
    is_stale: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
