"""Run one extraction job end to end (PRD 4.4, 6.11). The pipeline is DB-free; this module loads context, calls it and persists."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.context_builder import CategoryInfo
from app.ai.extraction_pipeline import Existing, ExtractionFailed, PipelineInput, run_extraction
from app.ai.providers import (
    ProviderOutputError,
    ProviderPermanentError,
    ProviderTransientError,
    get_llm_provider,
)
from app.ai.tag_matcher import RuleInfo, TagInfo
from app.ai.task_matcher import OpenTask
from app.core.config import get_settings
from app.core.time import get_zone
from app.models import (
    Activity,
    AIProcessingJob,
    JournalEntry,
    KeywordRule,
    Project,
    Tag,
    TagAlias,
    Task,
    User,
)
from app.models.enums import ActivityKind, ActivityStatus, AiJobStatus, EntryStatus, Placement, TaskStatus
from app.repositories.taxonomy import TaxonomyRepository
from app.repositories.users import UsersRepository
from app.services.review_service import persist_result

log = structlog.get_logger()
RETRY_DELAYS = [2, 8, 30]  # seconds, FR-052
MAX_ATTEMPTS = 3


async def build_input(session: AsyncSession, user: User, entry: JournalEntry, job: AIProcessingJob) -> PipelineInput:
    tax = TaxonomyRepository(session, user.id)
    prefs = await UsersRepository(session).preferences(user.id)
    cats = [CategoryInfo(c.id, c.name, c.path_names, c.root_kind.value, c.description, c.counts_as_focus, c.is_transition) for c in await tax.categories()]
    tags_raw = await tax.tags(include_archived=True)
    aliases = await tax.aliases_for([t.id for t in tags_raw])
    tags = [TagInfo(t.id, t.name, aliases.get(t.id, []), t.archived_at is not None, t.merged_into_id) for t in tags_raw]
    rules = [RuleInfo(r.phrase, r.target_type.value, r.tag_id or r.category_id) for r in await tax.rules()]  # type: ignore[arg-type]
    task_rows = (await session.execute(select(Task, Project.name).outerjoin(Project, Project.id == Task.project_id).where(
        Task.user_id == user.id, Task.deleted_at.is_(None), Task.status == TaskStatus.open).order_by(Task.created_at.desc()).limit(200))).all()
    tasks = [OpenTask(t.id, t.title, pname, t.priority) for t, pname in task_rows]
    lo, hi = entry.covers_start_at - timedelta(hours=12), entry.covers_end_at + timedelta(hours=12)
    existing_rows = (await session.execute(select(Activity).where(
        Activity.user_id == user.id, Activity.status == ActivityStatus.confirmed, Activity.kind == ActivityKind.actual, Activity.deleted_at.is_(None),
        ((Activity.start_at < hi) & (Activity.end_at > lo)) | ((Activity.placement == Placement.unplaced) & (Activity.local_date == entry.entry_date)),
        # An earlier run of this same entry is what Replace/Keep-both decides about, so it is not a "duplicate" of the new run.
        or_(Activity.journal_entry_id.is_(None), Activity.journal_entry_id != entry.id)))).scalars().all()
    existing = [Existing(a.id, a.title, a.placement.value, a.start_at, a.end_at, a.local_date, a.category_id, a.source_quote) for a in existing_rows]
    return PipelineInput(text=entry.raw_text, window_start=entry.covers_start_at, window_end=entry.covers_end_at, tz=get_zone(entry.timezone), tz_name=entry.timezone,
                         now=datetime.now(UTC), categories=cats, tags=tags, rules=rules, open_tasks=tasks, existing=existing,
                         gap_min_minutes=prefs.gap_min_minutes, hint=job.user_hint)


async def _fail(session: AsyncSession, job: AIProcessingJob, entry: JournalEntry | None, code: str) -> None:
    job.status, job.error_code, job.finished_at = AiJobStatus.failed, code, datetime.now(UTC)
    if entry is not None and entry.latest_job_id == job.id:
        entry.status = EntryStatus.failed
    await session.commit()


async def run_job(session: AsyncSession, job_id: uuid.UUID, provider=None) -> None:
    job = await session.get(AIProcessingJob, job_id)
    if job is None or job.status not in (AiJobStatus.queued, AiJobStatus.running):
        return
    entry = await session.get(JournalEntry, job.entry_id)
    user = await session.get(User, job.user_id)
    if job.status == AiJobStatus.queued:  # claimed by the runner already marks it running; direct calls (tests) do it here
        job.status, job.started_at, job.attempts = AiJobStatus.running, datetime.now(UTC), job.attempts + 1
        await session.commit()
    if entry is None or user is None or entry.deleted_at is not None:
        job.status, job.error_code, job.finished_at = AiJobStatus.cancelled, "ENTRY_GONE", datetime.now(UTC)
        await session.commit()
        return
    s = get_settings()
    try:
        inp = await build_input(session, user, entry, job)
        result = await run_extraction(inp, provider or get_llm_provider(), max_tokens=s.llm_max_tokens, timeout_s=s.llm_timeout_seconds)
    except ProviderTransientError as e:
        log.warning("extraction_provider_transient", job_id=str(job.id), attempt=job.attempts, reason=str(e))  # provider text only, never the journal
        if job.attempts < MAX_ATTEMPTS:
            job.status, job.queued_at = AiJobStatus.queued, datetime.now(UTC) + timedelta(seconds=RETRY_DELAYS[min(job.attempts, 3) - 1])
            await session.commit()
        else:
            await _fail(session, job, entry, "PROVIDER_UNAVAILABLE")
        return
    except ProviderPermanentError as e:
        log.error("extraction_provider_rejected", job_id=str(job.id), reason=str(e))  # e.g. "HTTP 400: tool_choice ... not supported": what to fix on the server
        await _fail(session, job, entry, "PROVIDER_ERROR")
        return
    except (ExtractionFailed, ProviderOutputError) as e:
        await _fail(session, job, entry, getattr(e, "code", "INVALID_MODEL_OUTPUT"))
        return
    except Exception:  # noqa: BLE001 - never lose the entry text; the job just fails and can be retried
        log.exception("extraction_job_crashed", job_id=str(job.id))
        await session.rollback()
        job = await session.get(AIProcessingJob, job_id)
        entry = await session.get(JournalEntry, job.entry_id)
        await _fail(session, job, entry, "INTERNAL")
        return
    await persist_result(session, user, entry, job, result)
    job.provider, job.model = result.llm.provider, result.llm.model  # what actually answered, not what was configured at submit time
    job.status, job.finished_at, job.error_code = AiJobStatus.succeeded, datetime.now(UTC), None
    if job.entry_revision != entry.revision:
        job.is_stale = True  # the text moved on while the job ran (PRD 6.11)
    if entry.latest_job_id == job.id:
        entry.status = EntryStatus.review
    await session.commit()


# keep imports referenced for type checkers
_ = (Tag, TagAlias, KeywordRule)
