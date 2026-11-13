"""A Postgres-backed queue over `ai_processing_jobs` (D-18): claim with FOR UPDATE SKIP LOCKED, no Redis.
Runs inside the API process by default (EMBEDDED_WORKER) or alone via `python -m app.workers.run`."""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update

from app.core.database import get_session_factory
from app.models import AIProcessingJob, JournalEntry
from app.models.enums import AiJobStatus, EntryStatus
from app.workers.tasks_ai import MAX_ATTEMPTS, run_job

log = structlog.get_logger()
STUCK_AFTER = timedelta(minutes=5)
POLL_SECONDS = 1.0


async def claim_next(session) -> AIProcessingJob | None:
    stmt = (select(AIProcessingJob).where(AIProcessingJob.status == AiJobStatus.queued, AIProcessingJob.queued_at <= datetime.now(UTC))
            .order_by(AIProcessingJob.queued_at).with_for_update(skip_locked=True).limit(1))
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is not None:
        job.status, job.started_at, job.attempts = AiJobStatus.running, datetime.now(UTC), job.attempts + 1
        await session.commit()
    return job


async def requeue_stuck(session) -> int:
    """A job `running` for more than 5 minutes lost its worker: retry it, or fail it after the last attempt."""
    cutoff = datetime.now(UTC) - STUCK_AFTER
    rows = (await session.execute(select(AIProcessingJob).where(AIProcessingJob.status == AiJobStatus.running, AIProcessingJob.started_at < cutoff).with_for_update(skip_locked=True))).scalars().all()
    for j in rows:
        if j.attempts >= MAX_ATTEMPTS:
            j.status, j.error_code, j.finished_at = AiJobStatus.failed, "TIMED_OUT", datetime.now(UTC)
            await session.execute(update(JournalEntry).where(JournalEntry.latest_job_id == j.id).values(status=EntryStatus.failed))
        else:
            j.status, j.queued_at = AiJobStatus.queued, datetime.now(UTC)
    await session.commit()
    return len(rows)


async def worker_loop(stop: asyncio.Event) -> None:
    factory = get_session_factory()
    last_sweep = 0.0
    log.info("worker_started")
    while not stop.is_set():
        try:
            async with factory() as s:
                if asyncio.get_event_loop().time() - last_sweep > 60:
                    await requeue_stuck(s)
                    last_sweep = asyncio.get_event_loop().time()
                job = await claim_next(s)
            if job is None:
                try:
                    await asyncio.wait_for(stop.wait(), timeout=POLL_SECONDS)
                except TimeoutError:
                    pass
                continue
            async with factory() as s:
                await run_job(s, job.id)
        except Exception:  # noqa: BLE001
            log.exception("worker_iteration_failed")
            await asyncio.sleep(2)
    log.info("worker_stopped")
