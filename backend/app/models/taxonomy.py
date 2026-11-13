import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUID_PK, Base, TimestampMixin, UserOwnedMixin
from app.models.enums import GoalKind, KeywordTarget, RootKind, pg_enum


class Category(Base, UserOwnedMixin, TimestampMixin):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id"))
    root_kind: Mapped[RootKind] = mapped_column(pg_enum(RootKind, "root_kind"))
    depth: Mapped[int] = mapped_column(SmallInteger)
    name: Mapped[str] = mapped_column(String(60))
    path_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))
    path_names: Mapped[str] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(7))
    description: Mapped[str | None] = mapped_column(String(300))
    counts_as_focus: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_system: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_transition: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Tag(Base, UserOwnedMixin, TimestampMixin):
    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    name: Mapped[str] = mapped_column(String(48))
    color: Mapped[str] = mapped_column(String(7))
    description: Mapped[str | None] = mapped_column(String(300))
    goal_kind: Mapped[GoalKind] = mapped_column(pg_enum(GoalKind, "goal_kind"), server_default="tracked")
    goal_weekly_minutes: Mapped[int | None] = mapped_column(Integer)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="SET NULL"))


class TagAlias(Base, UserOwnedMixin):
    __tablename__ = "tag_aliases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(48))


class KeywordRule(Base, UserOwnedMixin):
    __tablename__ = "keyword_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    phrase: Mapped[str] = mapped_column(String(60))
    target_type: Mapped[KeywordTarget] = mapped_column(pg_enum(KeywordTarget, "keyword_target"))
    tag_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="CASCADE"))
