import uuid
from datetime import date

from sqlalchemy import and_, delete, func, or_, select, update

from app.models import (
    Activity,
    ActivityDaySlice,
    ActivityTag,
    Category,
    IdealAllocation,
    IdealTemplate,
    KeywordRule,
    Tag,
    TagAlias,
)
from app.models.enums import IdealKind, RootKind
from app.repositories.base import UserScopedRepository


class TaxonomyRepository(UserScopedRepository):
    # ---- categories
    async def categories(self, include_archived: bool = False) -> list[Category]:
        stmt = select(Category).where(Category.user_id == self.user_id)
        if not include_archived:
            stmt = stmt.where(Category.archived_at.is_(None))
        stmt = stmt.order_by(Category.depth, Category.sort_order, func.lower(Category.name))
        return list((await self.session.execute(stmt)).scalars())

    async def category(self, id: uuid.UUID, *, for_update: bool = False) -> Category | None:
        return await self.get(Category, id, for_update=for_update)

    async def root(self, kind: RootKind) -> Category | None:
        stmt = select(Category).where(Category.user_id == self.user_id, Category.depth == 1, Category.root_kind == kind)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def subtree(self, category: Category) -> list[Category]:
        stmt = select(Category).where(Category.user_id == self.user_id, Category.path_ids.contains([category.id]))
        return list((await self.session.execute(stmt)).scalars())

    async def children(self, parent_id: uuid.UUID) -> list[Category]:
        stmt = select(Category).where(Category.user_id == self.user_id, Category.parent_id == parent_id)
        return list((await self.session.execute(stmt)).scalars())

    async def sibling_name_taken(self, parent_id: uuid.UUID, name: str, exclude: uuid.UUID | None = None) -> bool:
        stmt = select(func.count()).select_from(Category).where(
            Category.user_id == self.user_id, Category.parent_id == parent_id, func.lower(Category.name) == name.lower()
        )
        if exclude:
            stmt = stmt.where(Category.id != exclude)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def activity_count_for_categories(self, category_ids: list[uuid.UUID]) -> int:
        stmt = select(func.count()).select_from(Activity).where(
            Activity.user_id == self.user_id, Activity.category_id.in_(category_ids), Activity.deleted_at.is_(None)
        )
        return (await self.session.execute(stmt)).scalar_one()

    async def any_activity_for_categories(self, category_ids: list[uuid.UUID]) -> bool:
        """Includes soft-deleted rows: they can be restored, so history still references the category."""
        stmt = select(func.count()).select_from(Activity).where(
            Activity.user_id == self.user_id, Activity.category_id.in_(category_ids)
        )
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def repoint_activities(self, from_ids: list[uuid.UUID], to_id: uuid.UUID) -> int:
        res = await self.session.execute(
            update(Activity).where(Activity.user_id == self.user_id, Activity.category_id.in_(from_ids)).values(category_id=to_id)
        )
        await self.session.execute(
            update(ActivityDaySlice)
            .where(ActivityDaySlice.user_id == self.user_id, ActivityDaySlice.category_id.in_(from_ids))
            .values(category_id=to_id)
        )
        return res.rowcount or 0

    async def active_allocations(self, category_ids: list[uuid.UUID]) -> list[IdealAllocation]:
        """Allocations in the latest version of each ideal kind (the ones currently in force or upcoming)."""
        latest = (
            select(IdealTemplate.kind, func.max(IdealTemplate.effective_from).label("ef"))
            .where(IdealTemplate.user_id == self.user_id)
            .group_by(IdealTemplate.kind)
            .subquery()
        )
        stmt = (
            select(IdealAllocation)
            .join(IdealTemplate, IdealTemplate.id == IdealAllocation.template_id)
            .join(latest, and_(latest.c.kind == IdealTemplate.kind, latest.c.ef == IdealTemplate.effective_from))
            .where(IdealAllocation.user_id == self.user_id, IdealAllocation.category_id.in_(category_ids))
        )
        return list((await self.session.execute(stmt)).scalars())

    async def any_allocation(self, category_id: uuid.UUID) -> bool:
        stmt = select(func.count()).select_from(IdealAllocation).where(IdealAllocation.user_id == self.user_id, IdealAllocation.category_id == category_id)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def move_allocations(self, from_id: uuid.UUID, to_id: uuid.UUID) -> int:
        """Merge allocations of a category into another, summing where both exist (FR-089)."""
        moved = 0
        rows = (await self.session.execute(select(IdealAllocation).where(IdealAllocation.user_id == self.user_id, IdealAllocation.category_id == from_id))).scalars().all()
        for a in rows:
            existing = (await self.session.execute(
                select(IdealAllocation).where(IdealAllocation.template_id == a.template_id, IdealAllocation.category_id == to_id)
            )).scalar_one_or_none()
            if existing:
                existing.minutes += a.minutes
                await self.session.delete(a)
            else:
                a.category_id = to_id
            moved += 1
        return moved

    async def move_keyword_rules(self, from_id: uuid.UUID, to_id: uuid.UUID) -> None:
        rules = (await self.session.execute(select(KeywordRule).where(KeywordRule.user_id == self.user_id, KeywordRule.category_id == from_id))).scalars().all()
        for r in rules:
            dup = (await self.session.execute(select(KeywordRule).where(
                KeywordRule.user_id == self.user_id, KeywordRule.phrase == r.phrase, KeywordRule.category_id == to_id))).scalar_one_or_none()
            if dup:
                await self.session.delete(r)
            else:
                r.category_id = to_id

    async def ideal_day_allocations(self, on: date) -> list[IdealAllocation]:
        tpl = (await self.session.execute(
            select(IdealTemplate)
            .where(IdealTemplate.user_id == self.user_id, IdealTemplate.kind == IdealKind.day, IdealTemplate.effective_from <= on)
            .order_by(IdealTemplate.effective_from.desc()).limit(1))).scalar_one_or_none()
        if not tpl:
            return []
        return list((await self.session.execute(select(IdealAllocation).where(IdealAllocation.template_id == tpl.id))).scalars())

    # ---- tags
    async def tags(self, include_archived: bool = False, q: str | None = None) -> list[Tag]:
        stmt = select(Tag).where(Tag.user_id == self.user_id)
        if not include_archived:
            stmt = stmt.where(Tag.archived_at.is_(None))
        if q:
            stmt = stmt.where(Tag.name.ilike(f"%{q.lstrip('#').lower()}%"))
        return list((await self.session.execute(stmt.order_by(Tag.name))).scalars())

    async def tag(self, id: uuid.UUID, *, for_update: bool = False) -> Tag | None:
        return await self.get(Tag, id, for_update=for_update)

    async def tag_by_name(self, name: str) -> Tag | None:
        return (await self.session.execute(select(Tag).where(Tag.user_id == self.user_id, Tag.name == name))).scalar_one_or_none()

    async def tag_in_use(self, tag_id: uuid.UUID) -> bool:
        return (await self.session.execute(select(func.count()).select_from(ActivityTag).where(ActivityTag.tag_id == tag_id))).scalar_one() > 0

    async def aliases_for(self, tag_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        out: dict[uuid.UUID, list[str]] = {t: [] for t in tag_ids}
        if tag_ids:
            for a in (await self.session.execute(select(TagAlias).where(TagAlias.tag_id.in_(tag_ids)).order_by(TagAlias.alias))).scalars():
                out[a.tag_id].append(a.alias)
        return out

    async def alias_owner(self, alias: str) -> TagAlias | None:
        return (await self.session.execute(select(TagAlias).where(TagAlias.user_id == self.user_id, func.lower(TagAlias.alias) == alias.lower()))).scalar_one_or_none()

    async def replace_aliases(self, tag_id: uuid.UUID, aliases: list[str]) -> None:
        await self.session.execute(delete(TagAlias).where(TagAlias.tag_id == tag_id))
        for a in aliases:
            self.session.add(TagAlias(user_id=self.user_id, tag_id=tag_id, alias=a))
        await self.session.flush()

    async def tag_minutes(self, from_date: date, to_date: date, tag_ids: list[uuid.UUID] | None = None) -> dict[uuid.UUID, int]:
        stmt = (
            select(ActivityTag.tag_id, func.coalesce(func.sum(ActivityDaySlice.minutes), 0))
            .join(ActivityDaySlice, ActivityDaySlice.activity_id == ActivityTag.activity_id)
            .where(ActivityTag.user_id == self.user_id, ActivityDaySlice.local_date.between(from_date, to_date))
            .group_by(ActivityTag.tag_id)
        )
        if tag_ids is not None:
            stmt = stmt.where(ActivityTag.tag_id.in_(tag_ids))
        return {tid: int(m) for tid, m in (await self.session.execute(stmt)).all()}

    async def tag_minutes_by_day(self, tag_id: uuid.UUID, from_date: date, to_date: date) -> dict[date, int]:
        stmt = (
            select(ActivityDaySlice.local_date, func.sum(ActivityDaySlice.minutes))
            .join(ActivityTag, ActivityTag.activity_id == ActivityDaySlice.activity_id)
            .where(ActivityTag.tag_id == tag_id, ActivityDaySlice.user_id == self.user_id, ActivityDaySlice.local_date.between(from_date, to_date))
            .group_by(ActivityDaySlice.local_date)
        )
        return {d: int(m) for d, m in (await self.session.execute(stmt)).all()}

    # ---- keyword rules
    async def rules(self, target_type=None, target_id: uuid.UUID | None = None) -> list[KeywordRule]:
        stmt = select(KeywordRule).where(KeywordRule.user_id == self.user_id)
        if target_type:
            stmt = stmt.where(KeywordRule.target_type == target_type)
        if target_id:
            stmt = stmt.where(or_(KeywordRule.tag_id == target_id, KeywordRule.category_id == target_id))
        return list((await self.session.execute(stmt.order_by(KeywordRule.phrase))).scalars())
