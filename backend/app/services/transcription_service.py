"""Server-side transcription fallback (FR-016, E-27). The audio lives in memory for the length of the request and is never written
anywhere; the transcript is returned and not stored or logged (NFR-05)."""

from app.ai.providers import get_stt_provider
from app.ai.providers.base import ProviderPermanentError, ProviderTransientError
from app.core.config import get_settings
from app.core.errors import AppError, RateLimited
from app.core.rate_limit import limiter
from app.models import User

ALLOWED = {"audio/webm", "video/webm", "audio/ogg", "audio/mp4", "video/mp4", "audio/x-m4a", "audio/m4a", "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave"}
MIN_BYTES = 1024
EXT = {"webm": "webm", "ogg": "ogg", "mp4": "m4a", "mpeg": "mp3", "wav": "wav"}


def sniff(b: bytes) -> str | None:
    """What the bytes really are, so a renamed file or a hostile upload is refused before it goes anywhere."""
    if b[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if b[:4] == b"OggS":
        return "ogg"
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":
        return "wav"
    if b[4:8] == b"ftyp":
        return "mp4"
    if b[:3] == b"ID3" or (len(b) > 1 and b[0] == 0xFF and (b[1] & 0xE0) == 0xE0):
        return "mpeg"
    return None


class TranscriptionService:
    def __init__(self, user: User):
        self.user = user

    async def transcribe(self, audio: bytes, content_type: str | None, language: str | None, duration_hint: float | None) -> dict:
        s = get_settings()
        provider = get_stt_provider()
        if provider is None:
            raise AppError("Server transcription is not set up. Dictate in Chrome, Edge or Safari, or type.", code="STT_NOT_CONFIGURED", status=503)
        base_type = (content_type or "").split(";")[0].strip().lower()
        if len(audio) > s.stt_max_bytes:
            raise AppError(f"Recordings are limited to {s.stt_max_bytes // (1024 * 1024)} MB", code="AUDIO_TOO_LARGE", status=413)
        kind = sniff(audio)
        if base_type not in ALLOWED or kind is None or len(audio) < MIN_BYTES:
            raise AppError("That is not a usable audio recording. Try again, or type your entry.", code="UNSUPPORTED_AUDIO", status=422)
        if duration_hint is not None and duration_hint > 600:
            raise AppError("Recordings are limited to 10 minutes", code="AUDIO_TOO_LONG", status=422)
        key = f"stt:{self.user.id}"
        if limiter.hit(key, 3600) > s.stt_per_hour:
            raise RateLimited(limiter.retry_after(key, 3600), f"At most {s.stt_per_hour} recordings an hour can be transcribed")
        try:
            result = await provider.transcribe(audio, f"audio.{EXT[kind]}", base_type or "audio/webm", language, s.stt_timeout_seconds)
        except ProviderTransientError as e:
            raise AppError("Transcription is busy or unreachable. Try again in a moment, or type.", code="STT_UNAVAILABLE", status=502) from e
        except ProviderPermanentError as e:
            raise AppError("Transcription is misconfigured on the server.", code="STT_MISCONFIGURED", status=502) from e
        return {"text": result.text, "duration_s": round(duration_hint) if duration_hint is not None else None, "provider": result.provider}
