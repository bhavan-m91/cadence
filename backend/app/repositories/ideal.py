import uuid
from datetime import date

from sqlalchemy import delete, func, select

from app.models import ActivityDaySlice, Category, IdealAllocation, IdealTemplate
from app.models.enums import IdealKind
from app.repositories.base import UserScopedRepository


class IdealRepository(UserScopedRepository):
    async def effective(self, kind: IdealKind, on: date) -> IdealTemplate | None:
        """The version in force on `on`: the row with the greatest effective_from <= on (FR-111)."""
        stmt = (
            select(IdealTemplate)
            .where(IdealTemplate.user_id == self.user_id, IdealTemplate.kind == kind, IdealTemplate.effective_from <= on)
            .order_by(IdealTemplate.effective_from.desc()).limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def versions(self, kind: IdealKind) -> list[IdealTemplate]:
        stmt = select(IdealTemplate).where(IdealTemplate.user_id == self.user_id, IdealTemplate.kind == kind).order_by(IdealTemplate.effective_from.desc())
        return list((await self.session.execute(stmt)).scalars())

    async def allocations(self, template_id: uuid.UUID) -> list[IdealAllocation]:
        return list((await self.session.execute(select(IdealAllocation).where(IdealAllocation.template_id == template_id))).scalars())

    async def replace_template(self, kind: IdealKind, effective_from: date) -> IdealTemplate:
        """A second save for the same date replaces the first (PRD 5.2). Allocations cascade."""
        await self.session.execute(delete(IdealTemplate).where(
            IdealTemplate.user_id == self.user_id, IdealTemplate.kind == kind, IdealTemplate.effective_from == effective_from))
        tpl = IdealTemplate(user_id=self.user_id, kind=kind, effective_from=effective_from)
        self.session.add(tpl)
        await self.session.flush()
        return tpl

    async def minutes_by_day_and_category(self, from_date: date, to_date: date) -> dict[tuple[date, uuid.UUID], int]:
        stmt = (
            select(ActivityDaySlice.local_date, ActivityDaySlice.category_id, func.sum(ActivityDaySlice.minutes))
            .where(ActivityDaySlice.user_id == self.user_id, ActivityDaySlice.local_date.between(from_date, to_date))
            .group_by(ActivityDaySlice.local_date, ActivityDaySlice.category_id)
        )
        return {(d, c): int(m) for d, c, m in (await self.session.execute(stmt)).all()}

    async def categories_by_id(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, Category]:
        if not ids:
            return {}
        rows = (await self.session.execute(select(Category).where(Category.user_id == self.user_id, Category.id.in_(ids)))).scalars()
        return {c.id: c for c in rows}

    async def all_categories(self) -> list[Category]:
        return list((await self.session.execute(select(Category).where(Category.user_id == self.user_id))).scalars())
