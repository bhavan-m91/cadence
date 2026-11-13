"""OpenAI transcription adapter. The audio is sent once and not kept; neither the audio nor the text is logged."""

import time

import httpx

from app.ai.providers.base import ProviderPermanentError, ProviderTransientError, TranscriptionResult

URL = "https://api.openai.com/v1/audio/transcriptions"


class OpenAITranscriber:
    name = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model

    async def transcribe(self, audio: bytes, filename: str, content_type: str, language: str | None, timeout_s: int) -> TranscriptionResult:
        data = {"model": self.model, "response_format": "json"}
        if language:
            data["language"] = language
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                r = await client.post(URL, headers={"Authorization": f"Bearer {self.api_key}"}, data=data, files={"file": (filename, audio, content_type)})
        except httpx.TimeoutException as e:
            raise ProviderTransientError("transcription timed out") from e
        except httpx.HTTPError as e:
            raise ProviderTransientError("transcription service unreachable") from e
        if r.status_code in (401, 403):
            raise ProviderPermanentError("the transcription key was rejected")
        if r.status_code == 429 or r.status_code >= 500:
            raise ProviderTransientError(f"transcription service answered {r.status_code}")
        if r.status_code >= 400:
            raise ProviderPermanentError(f"transcription request refused ({r.status_code})")
        text = str(r.json().get("text", "")).strip()
        return TranscriptionResult(text=text, model=self.model, provider=self.name, latency_ms=int((time.monotonic() - started) * 1000))
