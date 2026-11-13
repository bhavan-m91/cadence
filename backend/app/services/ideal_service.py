"""Ideal Day and Ideal Week: exact-total validation, versioning by effective date, and actual-vs-ideal comparison (M7)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.metrics import pace_expected, per_day_minutes, prorate, row_status
from app.core.database import rolls_back_on_error
from app.core.errors import AppError, ValidationFailed
from app.core.time import date_range, elapsed_minutes, get_zone, week_start_date
from app.models import Category, IdealAllocation, IdealTemplate, User
from app.models.enums import IdealDistribution, IdealKind, RootKind
from app.repositories.ideal import IdealRepository
from app.repositories.users import UsersRepository
from app.schemas.ideal import (
    AllocationIn,
    AllocationOut,
    IdealOverviewOut,
    IdealSaveIn,
    IdealTemplateOut,
    IdealVersion,
    ProgressOut,
    ProgressRow,
)

TOTALS = {IdealKind.day: 1440, IdealKind.week: 10080}
ROOT_ORDER = {RootKind.work: 0, RootKind.personal: 1, RootKind.sleep: 2}


def _err(code: str, message: str, details: dict | None = None) -> AppError:
    return AppError(message, code=code, status=422, details=details or {})


class IdealService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = IdealRepository(session, user.id)
        self.tz = get_zone(user.timezone)

    def today(self) -> date:
        return datetime.now(UTC).astimezone(self.tz).date()

    # ------------------------------------------------------------------ read
    async def _out(self, kind: IdealKind, tpl: IdealTemplate | None, allocs: list[IdealAllocation] | None = None,
                   effective_from: date | None = None) -> IdealTemplateOut:
        rows = allocs if allocs is not None else (await self.repo.allocations(tpl.id) if tpl else [])
        cats = await self.repo.categories_by_id([a.category_id for a in rows])
        out = []
        for a in rows:
            c = cats[a.category_id]
            out.append(AllocationOut(
                category_id=c.id, name=c.name, path_names=c.path_names, color=c.color, root_kind=c.root_kind, minutes=a.minutes,
                distribution=a.distribution, per_day_minutes=per_day_minutes(a.minutes, a.distribution) if kind == IdealKind.week else None))
        out.sort(key=lambda r: (ROOT_ORDER[r.root_kind], r.path_names))
        total = sum(r.minutes for r in out)
        return IdealTemplateOut(kind=kind.value, effective_from=effective_from or (tpl.effective_from if tpl else None), allocations=out,
                                total_minutes=total, expected_minutes=TOTALS[kind], unallocated_minutes=TOTALS[kind] - total)

    async def overview(self, kind: IdealKind, on: date | None) -> IdealOverviewOut:
        tpl = await self.repo.effective(kind, on or self.today())
        versions = []
        for v in await self.repo.versions(kind):
            total = sum(a.minutes for a in await self.repo.allocations(v.id))
            versions.append(IdealVersion(effective_from=v.effective_from, created_at=v.created_at, total_minutes=total))
        return IdealOverviewOut(current=await self._out(kind, tpl) if tpl else None, versions=versions)

    # ------------------------------------------------------------------ validate + save
    async def _validate(self, kind: IdealKind, allocs: list[AllocationIn]) -> list[tuple[AllocationIn, Category]]:
        expected = TOTALS[kind]
        cats = await self.repo.categories_by_id([a.category_id for a in allocs])
        pairs: list[tuple[AllocationIn, Category]] = []
        seen: set[uuid.UUID] = set()
        for i, a in enumerate(allocs):
            cat = cats.get(a.category_id)
            if cat is None:
                raise ValidationFailed("Unknown category", path=f"allocations.{i}.category_id", rule="not_found")
            if a.minutes <= 0 or a.minutes % 5 != 0 or a.minutes > expected:
                raise _err("INVALID_MINUTES", "Minutes must be a positive multiple of 5", {"category_id": str(cat.id), "minutes": a.minutes})
            if cat.id in seen:
                raise _err("DUPLICATE_ALLOCATION", "A category can only appear once", {"category_id": str(cat.id)})
            seen.add(cat.id)
            if cat.archived_at is not None:
                raise _err("CATEGORY_ARCHIVED", "That category is archived", {"category_id": str(cat.id)})
            pairs.append((a, cat))
        for _, c1 in pairs:  # antichain: no allocated node may be an ancestor of another (FR-107)
            for _, c2 in pairs:
                if c1.id != c2.id and c1.id in c2.path_ids:
                    raise _err("ALLOCATION_NOT_ANTICHAIN", "A category and one inside it cannot both be allocated",
                               {"ancestor_id": str(c1.id), "descendant_id": str(c2.id)})
        actual = sum(a.minutes for a, _ in pairs)
        if actual != expected:
            raise _err("ALLOCATION_TOTAL_MISMATCH", f"Allocations must add up to exactly {expected} minutes",
                       {"expected": expected, "actual": actual, "delta": actual - expected})
        return pairs

    @rolls_back_on_error
    async def save(self, kind: IdealKind, body: IdealSaveIn, dry_run: bool) -> IdealTemplateOut:
        pairs = await self._validate(kind, body.allocations)
        dist = lambda a: IdealDistribution.all_days if kind == IdealKind.day else a.distribution  # noqa: E731
        if dry_run:
            fake = [IdealAllocation(category_id=c.id, minutes=a.minutes, distribution=dist(a)) for a, c in pairs]
            return await self._out(kind, None, fake, body.effective_from)
        tpl = await self.repo.replace_template(kind, body.effective_from)
        rows = [IdealAllocation(template_id=tpl.id, user_id=self.user.id, category_id=c.id, minutes=a.minutes, distribution=dist(a)) for a, c in pairs]
        self.session.add_all(rows)
        await self.session.flush()
        await UsersRepository(self.session).bump_revision(self.user.id)
        await self.session.commit()
        return await self._out(kind, tpl, rows)

    # ------------------------------------------------------------------ actual vs ideal (FR-118)
    async def progress(self, scope: Literal["day", "week"], on: date | None) -> ProgressOut:
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        today = self.today()
        anchor = on or today
        if scope == "day":
            from_d = to_d = anchor
            kind = IdealKind.day
        else:
            from_d = week_start_date(anchor, prefs.week_start)
            to_d = from_d + timedelta(days=6)
            kind = IdealKind.week
        week = date_range(from_d, to_d)
        as_of = min(today, to_d) if today >= from_d else from_d - timedelta(days=1)
        provisional = from_d <= today <= to_d

        tpl = await self.repo.effective(kind, from_d)  # the version in force on the first day of the range
        allocs = await self.repo.allocations(tpl.id) if tpl else []
        cats = {c.id: c for c in await self.repo.all_categories()}
        allocated_ids = {a.category_id for a in allocs}

        minutes = await self.repo.minutes_by_day_and_category(from_d, to_d)
        actual_by_alloc: dict[uuid.UUID, int] = {a.category_id: 0 for a in allocs}
        other = 0
        for (d, cid), m in minutes.items():
            if scope == "week" and d > as_of:
                continue
            owner = next((x for x in (cats[cid].path_ids if cid in cats else []) if x in allocated_ids), None)
            if owner is None:
                other += m
            else:
                actual_by_alloc[owner] += m

        rows: list[ProgressRow] = []
        for a in allocs:
            c = cats[a.category_id]
            if scope == "day":
                elapsed = elapsed_minutes(from_d, self.tz)
                if from_d == today:
                    now = datetime.now(UTC)
                    from app.core.time import day_start
                    elapsed_now = int((now - day_start(from_d, self.tz)).total_seconds() // 60)
                    expected = prorate(a.minutes, elapsed_now, elapsed)
                else:
                    expected = a.minutes if from_d < today else 0
            else:
                expected = pace_expected(a.minutes, a.distribution, week, as_of) if as_of >= from_d else 0
            actual = actual_by_alloc[a.category_id]
            delta = actual - expected
            rows.append(ProgressRow(category_id=c.id, name=c.name, path_names=c.path_names, color=c.color, root_kind=c.root_kind,
                                    distribution=a.distribution, target=a.minutes, expected_to_date=expected, actual=actual, delta=delta,
                                    status=row_status(delta, a.minutes)))
        rows.sort(key=lambda r: (ROOT_ORDER[r.root_kind], r.path_names))
        return ProgressOut(scope=scope, from_date=from_d, to_date=to_d, as_of=as_of, template_effective_from=tpl.effective_from if tpl else None,
                           provisional=provisional, rows=rows, other_actual=other, total_target=sum(r.target for r in rows),
                           total_actual=sum(r.actual for r in rows))


__all__ = ["IdealService", "select"]
