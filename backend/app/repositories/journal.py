import base64
import uuid
from datetime import date, datetime

from sqlalchemy import and_, func, or_, select

from app.models import (
    Activity,
    ActivityDaySlice,
    ActivityTag,
    AIProcessingJob,
    JournalEntry,
    JournalEntryRevision,
    Tag,
)
from app.models.enums import ActivityStatus, AiJobStatus, EntryStatus
from app.repositories.base import UserScopedRepository


def encode_cursor(entry_date: date, created_at: datetime, id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{entry_date.isoformat()}|{created_at.isoformat()}|{id}".encode()).decode()


def decode_cursor(c: str) -> tuple[date, datetime, uuid.UUID]:
    d, t, i = base64.urlsafe_b64decode(c.encode()).decode().split("|")
    return date.fromisoformat(d), datetime.fromisoformat(t), uuid.UUID(i)


class JournalRepository(UserScopedRepository):
    async def entry(self, id: uuid.UUID, *, for_update: bool = False) -> JournalEntry | None:
        return await self.get(JournalEntry, id, for_update=for_update)

    async def overlapping_entries(self, start: datetime, end: datetime, exclude: uuid.UUID | None = None) -> list[JournalEntry]:
        stmt = select(JournalEntry).where(JournalEntry.user_id == self.user_id, JournalEntry.deleted_at.is_(None), JournalEntry.status != EntryStatus.draft,
                                          JournalEntry.covers_start_at < end, JournalEntry.covers_end_at > start)
        if exclude:
            stmt = stmt.where(JournalEntry.id != exclude)
        return list((await self.session.execute(stmt)).scalars())

    async def list_entries(self, *, from_date=None, to_date=None, status=None, q=None, limit: int, cursor=None) -> list[JournalEntry]:
        stmt = select(JournalEntry).where(JournalEntry.user_id == self.user_id, JournalEntry.deleted_at.is_(None))
        if from_date:
            stmt = stmt.where(JournalEntry.entry_date >= from_date)
        if to_date:
            stmt = stmt.where(JournalEntry.entry_date <= to_date)
        if status:
            stmt = stmt.where(JournalEntry.status == status)
        if q:
            stmt = stmt.where(JournalEntry.raw_text.ilike(f"%{q}%"))
        if cursor:
            d, t, i = cursor
            stmt = stmt.where(or_(JournalEntry.entry_date < d, and_(JournalEntry.entry_date == d, or_(JournalEntry.created_at < t, and_(JournalEntry.created_at == t, JournalEntry.id > i)))))
        stmt = stmt.order_by(JournalEntry.entry_date.desc(), JournalEntry.created_at.desc(), JournalEntry.id).limit(limit + 1)
        return list((await self.session.execute(stmt)).scalars())

    async def revisions(self, entry_id: uuid.UUID) -> list[JournalEntryRevision]:
        stmt = select(JournalEntryRevision).where(JournalEntryRevision.entry_id == entry_id, JournalEntryRevision.user_id == self.user_id).order_by(JournalEntryRevision.revision)
        return list((await self.session.execute(stmt)).scalars())

    async def has_revision(self, entry_id: uuid.UUID, revision: int) -> bool:
        stmt = select(func.count()).select_from(JournalEntryRevision).where(JournalEntryRevision.entry_id == entry_id, JournalEntryRevision.revision == revision)
        return (await self.session.execute(stmt)).scalar_one() > 0

    async def job(self, id: uuid.UUID) -> AIProcessingJob | None:
        stmt = select(AIProcessingJob).where(AIProcessingJob.id == id, AIProcessingJob.user_id == self.user_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def latest_jobs(self, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, AIProcessingJob]:
        if not entry_ids:
            return {}
        stmt = select(AIProcessingJob).join(JournalEntry, JournalEntry.latest_job_id == AIProcessingJob.id).where(JournalEntry.id.in_(entry_ids))
        return {j.entry_id: j for j in (await self.session.execute(stmt)).scalars()}

    async def jobs_since(self, since: datetime, entry_id: uuid.UUID | None = None, regenerations_only: bool = False) -> int:
        stmt = select(func.count()).select_from(AIProcessingJob).where(AIProcessingJob.user_id == self.user_id, AIProcessingJob.created_at >= since)
        if entry_id:
            stmt = stmt.where(AIProcessingJob.entry_id == entry_id)
        if regenerations_only:
            stmt = stmt.where(AIProcessingJob.user_hint.is_not(None) | (AIProcessingJob.attempts >= 0))  # all jobs after the first for an entry
        return (await self.session.execute(stmt)).scalar_one()

    async def recent_equal_job(self, entry_id: uuid.UUID, text_hash: str, revision: int, prompt_version: str, since: datetime) -> AIProcessingJob | None:
        stmt = (select(AIProcessingJob).where(
            AIProcessingJob.user_id == self.user_id, AIProcessingJob.entry_id == entry_id, AIProcessingJob.text_hash == text_hash,
            AIProcessingJob.entry_revision == revision, AIProcessingJob.prompt_version == prompt_version, AIProcessingJob.created_at >= since,
            AIProcessingJob.status.in_([AiJobStatus.queued, AiJobStatus.running, AiJobStatus.succeeded]), AIProcessingJob.is_stale.is_(False))
            .order_by(AIProcessingJob.created_at.desc()).limit(1))
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def entry_activity_stats(self, entry_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
        """entry_id -> (confirmed activity count, minutes covered)."""
        out = {e: (0, 0) for e in entry_ids}
        if not entry_ids:
            return out
        stmt = (select(Activity.journal_entry_id, func.count(func.distinct(Activity.id)), func.coalesce(func.sum(ActivityDaySlice.minutes), 0))
                .outerjoin(ActivityDaySlice, ActivityDaySlice.activity_id == Activity.id)
                .where(Activity.user_id == self.user_id, Activity.journal_entry_id.in_(entry_ids), Activity.status == ActivityStatus.confirmed, Activity.deleted_at.is_(None))
                .group_by(Activity.journal_entry_id))
        for eid, n, m in (await self.session.execute(stmt)).all():
            out[eid] = (n, int(m))
        return out

    async def entry_tags(self, entry_ids: list[uuid.UUID], per_entry: int = 3) -> dict[uuid.UUID, list[Tag]]:
        out: dict[uuid.UUID, list[Tag]] = {e: [] for e in entry_ids}
        if not entry_ids:
            return out
        stmt = (select(Activity.journal_entry_id, Tag, func.count().label("n"))
                .join(ActivityTag, ActivityTag.activity_id == Activity.id).join(Tag, Tag.id == ActivityTag.tag_id)
                .where(Activity.user_id == self.user_id, Activity.journal_entry_id.in_(entry_ids), Activity.status == ActivityStatus.confirmed, Activity.deleted_at.is_(None))
                .group_by(Activity.journal_entry_id, Tag.id).order_by(func.count().desc(), Tag.name))
        for eid, tag, _ in (await self.session.execute(stmt)).all():
            if len(out[eid]) < per_entry:
                out[eid].append(tag)
        return out

    async def confirmed_entry_dates(self, since: date) -> set[date]:
        stmt = select(JournalEntry.entry_date).where(JournalEntry.user_id == self.user_id, JournalEntry.deleted_at.is_(None),
                                                      JournalEntry.status == EntryStatus.confirmed, JournalEntry.entry_date >= since).distinct()
        return {d for (d,) in (await self.session.execute(stmt)).all()}

    async def entries_count_since(self, since: date) -> int:
        stmt = select(func.count()).select_from(JournalEntry).where(JournalEntry.user_id == self.user_id, JournalEntry.deleted_at.is_(None),
                                                                     JournalEntry.status != EntryStatus.draft, JournalEntry.entry_date >= since)
        return (await self.session.execute(stmt)).scalar_one()

    async def logged_minutes_by_day(self, from_date: date, to_date: date) -> dict[date, int]:
        stmt = (select(ActivityDaySlice.local_date, func.sum(ActivityDaySlice.minutes)).where(
            ActivityDaySlice.user_id == self.user_id, ActivityDaySlice.local_date.between(from_date, to_date)).group_by(ActivityDaySlice.local_date))
        return {d: int(m) for d, m in (await self.session.execute(stmt)).all()}

    async def first_logged_date(self) -> date | None:
        return (await self.session.execute(select(func.min(ActivityDaySlice.local_date)).where(ActivityDaySlice.user_id == self.user_id))).scalar_one()
