import uuid
from typing import Annotated

from fastapi import APIRouter, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.api.deps import DB, CurrentUser
from app.core.idempotency import run_idempotent
from app.schemas.common import Envelope, ok
from app.schemas.review import AnswerIn, CommitIn, CommitOut, ReviewOut
from app.services.review_service import ReviewService

router = APIRouter(prefix="/journal-entries", tags=["review"])
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key")]


@router.get("/{entry_id}/review", response_model=Envelope[ReviewOut])
async def review(entry_id: uuid.UUID, user: CurrentUser, session: DB, job_id: uuid.UUID | None = None):
    return ok(await ReviewService(session, user).payload(entry_id, job_id))


@router.post("/{entry_id}/review/answers", response_model=Envelope[ReviewOut])
async def answer(entry_id: uuid.UUID, body: AnswerIn, user: CurrentUser, session: DB):
    return ok(await ReviewService(session, user).answer(entry_id, body.job_id, body.question_id, body.value))


@router.post("/{entry_id}/review/commit", response_model=Envelope[CommitOut])
async def commit(entry_id: uuid.UUID, body: CommitIn, user: CurrentUser, session: DB, idem: IdemKey = None):
    async def run():
        result = await ReviewService(session, user).commit(entry_id, body)
        return 200, {"data": jsonable_encoder(CommitOut.model_validate(result)), "meta": {}}

    status, payload = await run_idempotent(session, user.id, idem, f"commit:{entry_id}", body.model_dump(mode="json"), run)
    return JSONResponse(payload, status_code=status)
