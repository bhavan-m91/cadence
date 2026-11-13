import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Activity, Category
from app.repositories.activities import ActivitiesRepository
from app.repositories.taxonomy import TaxonomyRepository
from app.schemas.activity import ActivityOut, ActivityTagOut
from app.schemas.taxonomy import CategoryChip


def chip(c: Category) -> CategoryChip:
    return CategoryChip(id=c.id, name=c.name, path_names=c.path_names, color=c.color, root_kind=c.root_kind)


def tag_out(link, tag) -> ActivityTagOut:
    return ActivityTagOut(tag_id=tag.id, name=tag.name, color=tag.color, source=link.source.value, confidence=link.confidence, reason=link.reason)


async def activities_out(session: AsyncSession, user_id: uuid.UUID, activities: list[Activity]) -> list[ActivityOut]:
    if not activities:
        return []
    tax = TaxonomyRepository(session, user_id)
    cats = {c.id: c for c in await tax.get_many(Category, list({a.category_id for a in activities}))}
    tags = await ActivitiesRepository(session, user_id).tags_for([a.id for a in activities])
    out = []
    for a in activities:
        out.append(ActivityOut(
            id=a.id, title=a.title, description=a.description, status=a.status, kind=a.kind, placement=a.placement,
            start_at=a.start_at, end_at=a.end_at, window_start_at=a.window_start_at, window_end_at=a.window_end_at,
            duration_minutes=a.duration_minutes, time_certainty=a.time_certainty, timezone=a.timezone, local_date=a.local_date,
            category=chip(cats[a.category_id]), tags=[tag_out(l, t) for l, t in tags.get(a.id, [])], task_id=a.task_id,
            project_id=a.project_id, location_type=a.location_type, origin=a.origin, confidence=a.confidence,
            needs_review=a.needs_review, flags=list(a.flags or []), user_edited=a.user_edited, journal_entry_id=a.journal_entry_id,
            derived_from_id=a.derived_from_id, version=a.version, created_at=a.created_at, updated_at=a.updated_at,
        ))
    return out
