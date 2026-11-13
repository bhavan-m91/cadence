from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import CurrentUser
from app.core.config import get_settings
from app.schemas.common import Envelope, ok
from app.schemas.journal import TranscriptionOut
from app.services.transcription_service import TranscriptionService

router = APIRouter(tags=["transcriptions"])


@router.post("/transcriptions", response_model=Envelope[TranscriptionOut])
async def transcribe(user: CurrentUser, audio: Annotated[UploadFile, File()], language: Annotated[str | None, Form(max_length=12)] = None,
                     duration_s: Annotated[float | None, Form(ge=0, le=3600)] = None):
    limit = get_settings().stt_max_bytes
    data = await audio.read(limit + 1)  # one byte past the limit is enough to know it is too big
    return ok(await TranscriptionService(user).transcribe(data, audio.content_type, language, duration_s))
