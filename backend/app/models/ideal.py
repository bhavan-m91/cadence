import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import UUID_PK, Base, UserOwnedMixin
from app.models.enums import IdealDistribution, IdealKind, pg_enum


class IdealTemplate(Base, UserOwnedMixin):
    __tablename__ = "ideal_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    kind: Mapped[IdealKind] = mapped_column(pg_enum(IdealKind, "ideal_kind"))
    effective_from: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IdealAllocation(Base, UserOwnedMixin):
    __tablename__ = "ideal_allocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), **UUID_PK)
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ideal_templates.id", ondelete="CASCADE"))
    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"))
    minutes: Mapped[int] = mapped_column(Integer)
    distribution: Mapped[IdealDistribution] = mapped_column(pg_enum(IdealDistribution, "ideal_distribution"), server_default="all_days")
