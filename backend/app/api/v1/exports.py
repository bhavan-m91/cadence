import uuid

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.deps import DB, CurrentUser
from app.core.errors import NotFound
from app.models.enums import ExportStatus
from app.schemas.common import Envelope, ok
from app.schemas.user import ExportOut
from app.services import export_service

router = APIRouter(prefix="/exports", tags=["exports"])


@router.get("/{export_id}", response_model=Envelope[ExportOut])
async def get_export(export_id: uuid.UUID, user: CurrentUser, session: DB):
    job = await export_service.get_export(session, user, export_id)
    url = f"/api/v1/exports/{job.id}/download" if job.status == ExportStatus.succeeded else None
    return ok(ExportOut(id=job.id, status=job.status, download_url=url, expires_at=job.expires_at))


@router.get("/{export_id}/download")
async def download_export(export_id: uuid.UUID, user: CurrentUser, session: DB):
    job = await export_service.get_export(session, user, export_id)
    if job.status != ExportStatus.succeeded or not job.file_key:
        raise NotFound("Export not ready")
    return FileResponse(job.file_key, media_type="application/zip", filename="cadence-export.zip")
