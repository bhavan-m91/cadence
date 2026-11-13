import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse, Response

from app.api.deps import DB, CurrentUser, Limit
from app.core.idempotency import run_idempotent
from app.models.enums import EntryStatus
from app.schemas.common import Envelope, ok
from app.schemas.journal import (
    AiStatusOut,
    EntryCreate,
    EntryDetail,
    EntryOut,
    EntryPatch,
    EntrySummary,
    JobOut,
    ProcessIn,
    ProcessOut,
    RevisionOut,
    StatsOut,
)
from app.services.journal_service import JournalService

router = APIRouter(tags=["journal"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("/ai/status", response_model=Envelope[AiStatusOut])
async def ai_status(user: CurrentUser, session: DB):
    return ok(await JournalService(session, user).ai_status())


@router.post("/journal-entries", response_model=Envelope[EntryOut], status_code=201)
async def create_entry(body: EntryCreate, user: CurrentUser, session: DB):
    entry, overlaps = await JournalService(session, user).create(body)
    return ok(entry, overlaps=[{"id": str(o.id), "title": o.title or o.raw_text[:60], "covers_start_at": o.covers_start_at.isoformat(), "covers_end_at": o.covers_end_at.isoformat()} for o in overlaps])


@router.get("/journal-entries", response_model=Envelope[list[EntrySummary]])
async def list_entries(user: CurrentUser, session: DB, from_: Annotated[date | None, Query(alias="from")] = None, to: date | None = None,
                       status: EntryStatus | None = None, q: Annotated[str | None, Query(max_length=100)] = None, limit: Limit = 20, cursor: str | None = None):
    items, nxt = await JournalService(session, user).list(from_date=from_, to_date=to, status=status, q=q, limit=limit, cursor=cursor)
    return ok(items, next_cursor=nxt)


@router.get("/journal-entries/stats", response_model=Envelope[StatsOut])
async def stats(user: CurrentUser, session: DB, as_of_date: date | None = None):
    return ok(await JournalService(session, user).stats(as_of_date))


@router.get("/journal-entries/{entry_id}", response_model=Envelope[EntryDetail])
async def get_entry(entry_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await JournalService(session, user).detail(entry_id))


@router.patch("/journal-entries/{entry_id}", response_model=Envelope[EntryOut])
async def patch_entry(entry_id: uuid.UUID, body: EntryPatch, user: CurrentUser, session: DB):
    return ok(await JournalService(session, user).patch(entry_id, body))


@router.delete("/journal-entries/{entry_id}", status_code=204)
async def delete_entry(entry_id: uuid.UUID, user: CurrentUser, session: DB, activities: Annotated[str | None, Query(pattern="^(keep|delete)$")] = None):
    await JournalService(session, user).delete(entry_id, activities)
    return Response(status_code=204)


@router.get("/journal-entries/{entry_id}/revisions", response_model=Envelope[list[RevisionOut]])
async def revisions(entry_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await JournalService(session, user).revisions(entry_id))


@router.post("/journal-entries/{entry_id}/process", response_model=Envelope[ProcessOut], status_code=202)
async def process(entry_id: uuid.UUID, user: CurrentUser, session: DB, idem: IdemKey = None, body: ProcessIn | None = None):
    body = body or ProcessIn()

    async def run():
        job = await JournalService(session, user).process(entry_id, body.regenerate, body.user_hint)
        return 202, {"data": {"job_id": str(job.id), "status": job.status.value}, "meta": {}}

    status, payload = await run_idempotent(session, user.id, idem, f"process:{entry_id}", body.model_dump(mode="json"), run)
    return JSONResponse(payload, status_code=status)


@router.get("/ai-jobs/{job_id}", response_model=Envelope[JobOut])
async def get_job(job_id: uuid.UUID, user: CurrentUser, session: DB):
    return ok(await JournalService(session, user).job(job_id))
