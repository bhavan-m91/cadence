import uuid

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DB, CurrentUser
from app.models.enums import KeywordTarget
from app.schemas.common import Envelope, ok
from app.schemas.taxonomy import KeywordRuleCreate, KeywordRuleOut
from app.services.tag_service import TagService

router = APIRouter(prefix="/keyword-rules", tags=["keyword-rules"])


@router.get("", response_model=Envelope[list[KeywordRuleOut]])
async def list_rules(user: CurrentUser, session: DB, target_type: KeywordTarget | None = None, target_id: uuid.UUID | None = None):
    return ok(await TagService(session, user).list_rules(target_type, target_id))


@router.post("", response_model=Envelope[KeywordRuleOut], status_code=201)
async def create_rule(body: KeywordRuleCreate, user: CurrentUser, session: DB):
    return ok(await TagService(session, user).create_rule(body))


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: uuid.UUID, user: CurrentUser, session: DB):
    await TagService(session, user).delete_rule(rule_id)
    return Response(status_code=204)
