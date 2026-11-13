import httpx
import pytest

from app.ai.providers.base import ProviderPermanentError, ProviderTransientError
from app.ai.providers.stt_openai import OpenAITranscriber

pytestmark = pytest.mark.asyncio


def patch_client(monkeypatch, handler):
    real = httpx.AsyncClient

    class Client(real):
        def __init__(self, *a, **kw):
            super().__init__(*a, **{**kw, "transport": httpx.MockTransport(handler)})

    monkeypatch.setattr(httpx, "AsyncClient", Client)


async def test_it_sends_the_audio_and_model_once_and_returns_only_the_text(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"], seen["body"] = request.headers["authorization"], request.read()
        return httpx.Response(200, json={"text": "  lunch at one  "})

    patch_client(monkeypatch, handler)
    out = await OpenAITranscriber("sk-test", "gpt-4o-mini-transcribe").transcribe(b"\x1aE\xdf\xa3" + b"0" * 10, "audio.webm", "audio/webm", "en", 5)
    assert out.text == "lunch at one" and out.provider == "openai"
    assert seen["auth"] == "Bearer sk-test" and b"gpt-4o-mini-transcribe" in seen["body"] and b'name="language"' in seen["body"]


@pytest.mark.parametrize("status,error", [(401, ProviderPermanentError), (403, ProviderPermanentError), (400, ProviderPermanentError), (429, ProviderTransientError), (503, ProviderTransientError)])
async def test_failures_are_sorted_into_retryable_and_not(monkeypatch, status, error):
    patch_client(monkeypatch, lambda r: httpx.Response(status, json={"error": {"message": "nope"}}))
    with pytest.raises(error):
        await OpenAITranscriber("k", "m").transcribe(b"x" * 2000, "audio.webm", "audio/webm", None, 5)


async def test_a_timeout_is_retryable(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout("slow")

    patch_client(monkeypatch, handler)
    with pytest.raises(ProviderTransientError):
        await OpenAITranscriber("k", "m").transcribe(b"x" * 2000, "audio.webm", "audio/webm", None, 1)
