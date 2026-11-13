import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUID_PK, Base, TimestampMixin, UserOwnedMixin
from app.models.enums import (
    ActivityEventType,
    ActivityKind,
    ActivityOrigin,
    ActivityStatus,
    EventActor,
    LocationType,
    Placement,
    TagSource,
    TimeCertainty,
    pg_enum,
)


class Activity(Base, UserOwnedMixin, TimestampMixin):
    __tablename__ = "activities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="SET NULL"))
    source_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_processing_jobs.id", ondelete="SET NULL"))
    status: Mapped[ActivityStatus] = mapped_column(pg_enum(ActivityStatus, "activity_status"), server_default="confirmed")
    kind: Mapped[ActivityKind] = mapped_column(pg_enum(ActivityKind, "activity_kind"), server_default="actual")
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tasks.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"))
    location_type: Mapped[LocationType | None] = mapped_column(pg_enum(LocationType, "location_type"))
    placement: Mapped[Placement] = mapped_column(pg_enum(Placement, "placement"))
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    time_certainty: Mapped[TimeCertainty] = mapped_column(pg_enum(TimeCertainty, "time_certainty"), server_default="stated")
    timezone: Mapped[str] = mapped_column(String(64))
    local_date: Mapped[date] = mapped_column(Date)
    origin: Mapped[ActivityOrigin] = mapped_column(pg_enum(ActivityOrigin, "activity_origin"), server_default="manual")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    needs_review: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    flags: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    source_quote: Mapped[str | None] = mapped_column(Text)
    source_start: Mapped[int | None] = mapped_column(Integer)
    source_end: Mapped[int | None] = mapped_column(Integer)
    source_revision: Mapped[int | None] = mapped_column(Integer)
    ai_proposed: Mapped[dict | None] = mapped_column(JSONB)
    user_edited: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    derived_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"))
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"))
    version: Mapped[int] = mapped_column(Integer, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ActivityTag(Base):
    __tablename__ = "activity_tags"

    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="RESTRICT"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    source: Mapped[TagSource] = mapped_column(pg_enum(TagSource, "tag_source"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    reason: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityDaySlice(Base):
    __tablename__ = "activity_day_slices"

    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    minutes: Mapped[int] = mapped_column(SmallInteger)
    is_placed: Mapped[bool] = mapped_column(Boolean)
    slice_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    slice_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    time_certainty: Mapped[TimeCertainty] = mapped_column(pg_enum(TimeCertainty, "time_certainty"))
    location_type: Mapped[LocationType | None] = mapped_column(pg_enum(LocationType, "location_type"))


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    event_type: Mapped[ActivityEventType] = mapped_column(pg_enum(ActivityEventType, "activity_event_type"))
    actor: Mapped[EventActor] = mapped_column(pg_enum(EventActor, "event_actor"))
    payload: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
