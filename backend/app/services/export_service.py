"""Account data export as a ZIP of JSON files (FR-110). Built in a background task; downloadable for 24 hours."""

import io
import json
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.models import (
    Activity,
    ActivityDaySlice,
    ActivityEvent,
    ActivityTag,
    AIProcessingJob,
    Category,
    IdealAllocation,
    IdealTemplate,
    JournalEntry,
    JournalEntryRevision,
    KeywordRule,
    Project,
    Tag,
    TagAlias,
    Task,
    User,
    UserPreferences,
)
from app.models.enums import ExportStatus
from app.models.support import ExportJob

EXPORT_MODELS = [Category, Tag, TagAlias, KeywordRule, Project, Task, JournalEntry, JournalEntryRevision, AIProcessingJob,
                 Activity, ActivityTag, ActivityDaySlice, ActivityEvent, IdealTemplate, IdealAllocation]
EXPORT_TTL = timedelta(hours=24)


def _row(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def _default(v):
    if hasattr(v, "value"):
        return v.value
    return str(v)


async def request_export(session: AsyncSession, user: User) -> ExportJob:
    if user.email_verified_at is None:
        raise AppError("Verify your email before exporting your data", code="EMAIL_NOT_VERIFIED", status=403)
    job = ExportJob(user_id=user.id, status=ExportStatus.queued)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


async def run_export(session: AsyncSession, job_id: uuid.UUID) -> None:
    job = await session.get(ExportJob, job_id)
    if job is None:
        return
    job.status = ExportStatus.running
    await session.commit()
    try:
        user = await session.get(User, job.user_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            profile = _row(user) | {"password_hash": None, "google_sub": None}
            prefs = await session.get(UserPreferences, user.id)
            z.writestr("profile.json", json.dumps({"user": profile, "preferences": _row(prefs) if prefs else None}, default=_default, indent=2))
            for model in EXPORT_MODELS:
                rows = (await session.execute(select(model).where(model.user_id == user.id))).scalars().all()
                z.writestr(f"{model.__tablename__}.json", json.dumps([_row(r) for r in rows], default=_default, indent=2))
        out_dir = Path(get_settings().export_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{job.id}.zip"
        path.write_bytes(buf.getvalue())
        job.file_key, job.size_bytes = str(path), path.stat().st_size
        job.status, job.finished_at = ExportStatus.succeeded, datetime.now(UTC)
        job.expires_at = job.finished_at + EXPORT_TTL
    except Exception:  # noqa: BLE001
        job.status, job.error_code, job.finished_at = ExportStatus.failed, "EXPORT_FAILED", datetime.now(UTC)
    await session.commit()


async def get_export(session: AsyncSession, user: User, export_id: uuid.UUID) -> ExportJob:
    job = await session.get(ExportJob, export_id)
    if job is None or job.user_id != user.id:
        raise NotFound("Export not found")
    if job.status == ExportStatus.succeeded and job.expires_at and job.expires_at <= datetime.now(UTC):
        job.status = ExportStatus.expired
        await session.commit()
    return job
