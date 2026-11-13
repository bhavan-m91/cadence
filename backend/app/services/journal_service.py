"""Journal entries: capture, revisions, history, stats and submission for extraction (M2, FR-013..FR-028, FR-029, FR-050..FR-057)."""

import hashlib
import re
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context_builder import PROMPT_ID
from app.ai.providers import get_llm_provider, stt_status
from app.core.config import get_settings
from app.core.database import rolls_back_on_error
from app.core.errors import AppError, Conflict, NotFound, RateLimited, ValidationFailed
from app.core.time import date_range, elapsed_minutes, ensure_utc, floor_minute, get_zone, local_date_of
from app.models import Activity, AIProcessingJob, JournalEntry, JournalEntryRevision, User
from app.models.enums import ActivityStatus, AiJobStatus, EntryStatus
from app.repositories.journal import JournalRepository, decode_cursor, encode_cursor
from app.repositories.users import UsersRepository
from app.schemas.journal import (
    AiStatusOut,
    EntryCreate,
    EntryDetail,
    EntryPatch,
    EntrySummary,
    JobBrief,
    JobOut,
    StatsOut,
    TagDot,
    YesterdayGap,
)
from app.services import serializers
from app.services.activity_service import ActivityService
from app.services.timeline_service import TimelineService

DEDUPE_WINDOW = timedelta(minutes=10)
FUTURE_SLACK = timedelta(minutes=5)


def normalise_text(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def text_hash(t: str) -> str:
    return hashlib.sha256(normalise_text(t).encode()).hexdigest()


def display_title(e: JournalEntry) -> str:
    return e.title or (e.raw_text.strip().replace("\n", " ")[:60] or "Untitled entry")


def local_day_start_utc(user_tz: str, d: date) -> datetime:
    from app.core.time import day_start

    return day_start(d, get_zone(user_tz))


class JournalService:
    def __init__(self, session: AsyncSession, user: User):
        self.session, self.user = session, user
        self.repo = JournalRepository(session, user.id)

    async def _get(self, id: uuid.UUID, *, for_update: bool = False) -> JournalEntry:
        e = await self.repo.entry(id, for_update=for_update)
        if e is None:
            raise NotFound("Entry not found")
        return e

    def _window(self, start: datetime, end: datetime, tz_name: str) -> tuple[datetime, datetime]:
        tz = get_zone(tz_name)
        s, e = floor_minute(ensure_utc(start, tz)), floor_minute(ensure_utc(end, tz))
        if e <= s:
            raise ValidationFailed("The window must end after it starts", path="covers_end_at", rule="end_before_start")
        if e - s > timedelta(hours=24):
            raise AppError("A journal window can cover at most 24 hours", code="WINDOW_TOO_LONG", status=422)
        if e > datetime.now(UTC) + FUTURE_SLACK:
            raise AppError("The window cannot end in the future", code="WINDOW_IN_FUTURE", status=422)
        return s, e

    async def _snapshot(self, e: JournalEntry) -> None:
        """Revision rows start when an entry first leaves draft: revision 1 is then the text as first submitted (AC-007)."""
        if not await self.repo.has_revision(e.id, e.revision):
            self.session.add(JournalEntryRevision(entry_id=e.id, user_id=self.user.id, revision=e.revision, raw_text=e.raw_text,
                                                  covers_start_at=e.covers_start_at, covers_end_at=e.covers_end_at))
            await self.session.flush()

    # ------------------------------------------------------------------ create / edit
    @rolls_back_on_error
    async def create(self, body: EntryCreate) -> tuple[JournalEntry, list[JournalEntry]]:
        tz_name = body.timezone or self.user.timezone
        s, e = self._window(body.covers_start_at, body.covers_end_at, tz_name)
        entry = JournalEntry(user_id=self.user.id, entry_date=local_date_of(s, get_zone(tz_name)), covers_start_at=s, covers_end_at=e, timezone=tz_name,
                             raw_text=body.raw_text, text_hash=text_hash(body.raw_text), input_method=body.input_method, dictation_seconds=body.dictation_seconds,
                             status=EntryStatus.draft, revision=1, version=1)
        self.session.add(entry)
        await self.session.flush()
        overlaps = await self.repo.overlapping_entries(s, e, entry.id)  # a warning, never a block (FR-019)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry, overlaps

    @rolls_back_on_error
    async def patch(self, id: uuid.UUID, body: EntryPatch) -> JournalEntry:
        e = await self._get(id, for_update=True)
        if e.version != body.version:
            raise Conflict("This entry was changed elsewhere", code="VERSION_CONFLICT", details={"current_version": e.version})
        text_changed = body.raw_text is not None and body.raw_text != e.raw_text
        window_changed = (body.covers_start_at is not None or body.covers_end_at is not None)
        if window_changed:
            s, en = self._window(body.covers_start_at or e.covers_start_at, body.covers_end_at or e.covers_end_at, e.timezone)
            window_changed = (s, en) != (e.covers_start_at, e.covers_end_at)
        if text_changed or window_changed:
            if e.status != EntryStatus.draft:
                await self._snapshot(e)
                e.revision += 1
            if text_changed:
                e.raw_text, e.text_hash = body.raw_text, text_hash(body.raw_text)  # type: ignore[arg-type]
            if window_changed:
                e.covers_start_at, e.covers_end_at = s, en
                e.entry_date = local_date_of(s, get_zone(e.timezone))
            if e.status != EntryStatus.draft:
                await self.session.flush()
                self.session.add(JournalEntryRevision(entry_id=e.id, user_id=self.user.id, revision=e.revision, raw_text=e.raw_text,
                                                      covers_start_at=e.covers_start_at, covers_end_at=e.covers_end_at))
                if e.latest_job_id:  # a job that read the old text is stale (PRD 6.11)
                    await self.session.execute(update(AIProcessingJob).where(AIProcessingJob.id == e.latest_job_id).values(is_stale=True))
        if body.title is not None:
            e.title = body.title or None
        e.version += 1
        await self.session.commit()
        await self.session.refresh(e)
        return e

    async def revisions(self, id: uuid.UUID):
        await self._get(id)
        return await self.repo.revisions(id)

    # ------------------------------------------------------------------ read
    async def detail(self, id: uuid.UUID) -> EntryDetail:
        e = await self._get(id)
        acts = (await self.session.execute(select(Activity).where(
            Activity.user_id == self.user.id, Activity.journal_entry_id == e.id, Activity.status == ActivityStatus.confirmed, Activity.deleted_at.is_(None))
            .order_by(Activity.start_at.nulls_last(), Activity.created_at))).scalars().all()
        job = await self.repo.job(e.latest_job_id) if e.latest_job_id else None
        base = {c: getattr(e, c) for c in ("id", "entry_date", "title", "raw_text", "covers_start_at", "covers_end_at", "timezone", "input_method", "dictation_seconds",
                                            "status", "latest_job_id", "revision", "version", "created_at", "updated_at")}
        return EntryDetail(**base, activities=await serializers.activities_out(self.session, self.user.id, list(acts)),
                           latest_job=JobBrief(id=job.id, status=job.status.value, error_code=job.error_code, is_stale=job.is_stale, provider=job.provider, model=job.model) if job else None)

    async def list(self, *, from_date, to_date, status, q, limit: int, cursor: str | None) -> tuple[list[EntrySummary], str | None]:
        rows = await self.repo.list_entries(from_date=from_date, to_date=to_date, status=status, q=q, limit=limit, cursor=decode_cursor(cursor) if cursor else None)
        more = len(rows) > limit
        rows = rows[:limit]
        ids = [r.id for r in rows]
        stats, tags = await self.repo.entry_activity_stats(ids), await self.repo.entry_tags(ids)
        out = [EntrySummary(id=r.id, entry_date=r.entry_date, title=display_title(r), status=r.status, covers_start_at=r.covers_start_at, covers_end_at=r.covers_end_at,
                            timezone=r.timezone, input_method=r.input_method, word_count=len(r.raw_text.split()), activity_count=stats[r.id][0], covered_minutes=stats[r.id][1],
                            window_minutes=int((r.covers_end_at - r.covers_start_at).total_seconds() // 60), tags=[TagDot(name=t.name, color=t.color) for t in tags[r.id]]) for r in rows]
        return out, (encode_cursor(rows[-1].entry_date, rows[-1].created_at, rows[-1].id) if more and rows else None)

    @rolls_back_on_error
    async def delete(self, id: uuid.UUID, activities: str | None) -> None:
        e = await self._get(id, for_update=True)
        confirmed = (await self.session.execute(select(Activity).where(
            Activity.user_id == self.user.id, Activity.journal_entry_id == e.id, Activity.status == ActivityStatus.confirmed, Activity.deleted_at.is_(None)))).scalars().all()
        if confirmed and activities not in ("keep", "delete"):
            raise AppError("Choose whether to keep or delete this entry's activities", code="ACTIVITIES_CHOICE_REQUIRED", status=422)
        if activities == "delete":
            svc = ActivityService(self.session, self.user)
            for a in confirmed:
                await svc._soft_delete(a)
        else:
            for a in confirmed:
                a.user_edited = True  # "keep" marks them as manually owned (FR-024)
        await self.session.execute(delete(Activity).where(Activity.user_id == self.user.id, Activity.journal_entry_id == e.id, Activity.status == ActivityStatus.draft))
        e.deleted_at = datetime.now(UTC)
        await UsersRepository(self.session).bump_revision(self.user.id)
        await self.session.commit()

    # ------------------------------------------------------------------ stats (FR-027, FR-028)
    async def stats(self, as_of: date | None) -> StatsOut:
        tz = get_zone(self.user.timezone)
        today = as_of or datetime.now(UTC).astimezone(tz).date()
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        dates = await self.repo.confirmed_entry_dates(today - timedelta(days=400))
        cur = today if today in dates else today - timedelta(days=1)
        streak = 0
        while cur in dates:
            streak, cur = streak + 1, cur - timedelta(days=1)
        per_day = round(await self.repo.entries_count_since(today - timedelta(days=29)) / 30, 1)

        first = await self.repo.first_logged_date()
        pct: float | None = None
        gap: YesterdayGap | None = None
        if first is not None:
            start = max(first, today - timedelta(days=30))
            span = date_range(start, today - timedelta(days=1))
            if span:
                logged = await self.repo.logged_minutes_by_day(span[0], span[-1])
                full = sum(1 for d in span if elapsed_minutes(d, tz) - logged.get(d, 0) <= prefs.coverage_tolerance_minutes)
                pct = round(full / len(span), 3)
            y = today - timedelta(days=1)
            if first <= y:
                day = (await TimelineService(self.session, self.user).build(y, y, None, False)).days[0]
                if day.coverage.unlogged > prefs.coverage_tolerance_minutes and day.gaps:
                    g = max(day.gaps, key=lambda x: x.minutes)
                    gap = YesterdayGap(date=y, minutes=g.minutes, start_at=g.start_at, end_at=g.end_at)
        return StatsOut(streak_days=streak, entries_per_day_30d=per_day, full_days_pct_30d=pct, yesterday_gap=gap)

    # ------------------------------------------------------------------ submit for extraction
    async def used_today(self) -> int:
        tz = get_zone(self.user.timezone)
        start = local_day_start_utc(self.user.timezone, datetime.now(UTC).astimezone(tz).date())
        return await self.repo.jobs_since(start)

    async def ai_status(self) -> AiStatusOut:
        s = get_settings()
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        p = get_llm_provider()
        return AiStatusOut(provider=p.name, model=p.model, demo=p.name in ("fake", "fixture"), enabled=s.llm_enabled and prefs.ai_enabled,
                           daily_limit=s.ai_daily_job_limit, used_today=await self.used_today(), **stt_status())

    async def process(self, id: uuid.UUID, regenerate: bool, hint: str | None) -> AIProcessingJob:
        s = get_settings()
        e = await self._get(id, for_update=True)
        prefs = await UsersRepository(self.session).preferences(self.user.id)
        if not (s.llm_enabled and prefs.ai_enabled):  # AI off: the entry is saved as manual and no job exists (FR-053, AC-024)
            if e.status in (EntryStatus.draft, EntryStatus.failed):
                await self._snapshot(e)
                e.status = EntryStatus.manual
            await self.session.commit()
            raise AppError("AI is turned off. Add the activities by hand.", code="AI_DISABLED", status=422, details={"entry_id": str(e.id)})
        job = await self.repo.job(e.latest_job_id) if e.latest_job_id else None
        if job and job.status in (AiJobStatus.queued, AiJobStatus.running):
            raise Conflict("This entry is already being processed", code="ENTRY_BUSY", details={"job_id": str(job.id)})
        now = datetime.now(UTC)
        if not regenerate:
            same = await self.repo.recent_equal_job(e.id, e.text_hash, e.revision, PROMPT_ID, now - DEDUPE_WINDOW)
            if same is not None:  # FR-055: the same text within 10 minutes reuses the job
                return same
        tz = get_zone(self.user.timezone)
        day0 = local_day_start_utc(self.user.timezone, now.astimezone(tz).date())
        if await self.repo.jobs_since(day0) >= s.ai_daily_job_limit:
            reset = int((local_day_start_utc(self.user.timezone, now.astimezone(tz).date() + timedelta(days=1)) - now).total_seconds())
            raise RateLimited(reset, f"Daily limit of {s.ai_daily_job_limit} AI runs reached")
        if regenerate and await self.repo.jobs_since(day0, entry_id=e.id) > s.ai_regenerations_per_day:
            raise AppError(f"At most {s.ai_regenerations_per_day} regenerations per entry per day", code="AI_REGEN_LIMIT", status=429)
        await self._snapshot(e)
        p = get_llm_provider()
        job = AIProcessingJob(user_id=self.user.id, entry_id=e.id, status=AiJobStatus.queued, entry_revision=e.revision, text_hash=e.text_hash,
                              user_hint=(hint or None), prompt_version=PROMPT_ID, provider=p.name, model=p.model, queued_at=now)
        self.session.add(job)
        await self.session.flush()
        e.status, e.latest_job_id = EntryStatus.processing, job.id
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def job(self, job_id: uuid.UUID) -> JobOut:
        j = await self.repo.job(job_id)
        if j is None:
            raise NotFound("Job not found")
        return JobOut(id=j.id, status=j.status.value, attempts=j.attempts, error_code=j.error_code, entry_id=j.entry_id, is_stale=j.is_stale)


__all__ = ["JournalService", "display_title", "text_hash"]
