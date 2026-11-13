"""A transcriber for tests. It never runs in a real deployment (`STT_PROVIDER=fake` is refused outside test and dev)."""

from app.ai.providers.base import TranscriptionResult


class FakeTranscriber:
    name = "fake"
    model = "fake-stt"

    def __init__(self, text: str = "I worked on the proposal from nine to eleven and then had lunch.", error: Exception | None = None):
        self.text, self.error, self.calls = text, error, []

    async def transcribe(self, audio: bytes, filename: str, content_type: str, language: str | None, timeout_s: int) -> TranscriptionResult:
        self.calls.append({"bytes": len(audio), "filename": filename, "content_type": content_type, "language": language})
        if self.error:
            raise self.error
        return TranscriptionResult(text=self.text, model=self.model, provider=self.name, latency_ms=1)
