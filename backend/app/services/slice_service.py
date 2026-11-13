"""Derived day slices (D-15). Rebuilt inside every transaction that changes time, category, status, kind or deletion."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import compute_slices, get_zone, local_date_of
from app.models import Activity, ActivityDaySlice
from app.models.enums import ActivityKind, ActivityStatus, Placement
from app.repositories.activities import ActivitiesRepository


def counts_in_analytics(a: Activity) -> bool:
    return a.status == ActivityStatus.confirmed and a.kind == ActivityKind.actual and a.deleted_at is None


async def rebuild(session: AsyncSession, activity: Activity) -> None:
    await session.execute(
        ActivityDaySlice.__table__.delete().where(ActivityDaySlice.activity_id == activity.id)
    )
    if not counts_in_analytics(activity):
        return
    tz = get_zone(activity.timezone)
    common = dict(
        activity_id=activity.id, user_id=activity.user_id, category_id=activity.category_id,
        time_certainty=activity.time_certainty, location_type=activity.location_type,
    )
    if activity.placement == Placement.placed:
        for s in compute_slices(activity.start_at, activity.end_at, tz):
            session.add(ActivityDaySlice(**common, local_date=s.local_date, minutes=s.minutes, is_placed=True,
                                         slice_start_at=s.start, slice_end_at=s.end))
    else:
        session.add(ActivityDaySlice(**common, local_date=local_date_of(activity.window_start_at, tz),
                                     minutes=activity.duration_minutes, is_placed=False))
    await session.flush()


async def check_invariants(repo: ActivitiesRepository) -> list[dict]:
    """Nightly invariant: for each confirmed actual activity, sum of slice minutes == duration_minutes."""
    return await repo.slice_invariant_violations()
