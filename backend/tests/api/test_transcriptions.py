import pytest

from app.ai.providers import set_stt_provider
from app.ai.providers.base import ProviderPermanentError, ProviderTransientError
from app.ai.providers.stt_fake import FakeTranscriber
from app.core.rate_limit import limiter
from tests.factories import signup

pytestmark = pytest.mark.asyncio
API = "/api/v1"

WEBM = b"\x1aE\xdf\xa3" + b"\x00" * 2048
OGG = b"OggS" + b"\x00" * 2048
MP4 = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 2048


@pytest.fixture(autouse=True)
def _stt():
    fake = FakeTranscriber()
    set_stt_provider(fake)
    limiter.reset()
    yield fake
    set_stt_provider(None)


async def send(client, p, data=WEBM, ctype="audio/webm;codecs=opus", **form):
    return await client.post(f"{API}/transcriptions", headers=p.headers, files={"audio": ("rec.webm", data, ctype)}, data=form)


async def test_a_recording_comes_back_as_text_and_only_the_text(client, _stt):
    p = await signup(client)
    r = await send(client, p, language="en", duration_s="42.4")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"text": _stt.text, "duration_s": 42, "provider": "fake"}
    assert _stt.calls == [{"bytes": len(WEBM), "filename": "audio.webm", "content_type": "audio/webm", "language": "en"}]


@pytest.mark.parametrize("data,ctype", [(OGG, "audio/ogg"), (MP4, "audio/mp4")])
async def test_the_formats_other_browsers_record_are_accepted(client, data, ctype):
    p = await signup(client)
    assert (await send(client, p, data, ctype)).status_code == 200


async def test_ac009_status_tells_the_app_the_fallback_exists(client):
    p = await signup(client)
    s = (await client.get(f"{API}/ai/status", headers=p.headers)).json()["data"]
    assert s["stt_available"] is True and s["stt_provider"] == "fake"
    set_stt_provider(None)
    s = (await client.get(f"{API}/ai/status", headers=p.headers)).json()["data"]
    assert s["stt_available"] is False and s["stt_provider"] is None


async def test_without_a_provider_the_endpoint_says_so_instead_of_inventing_text(client):
    p = await signup(client)
    set_stt_provider(None)
    r = await send(client, p)
    assert r.status_code == 503 and r.json()["error"]["code"] == "STT_NOT_CONFIGURED"


async def test_oversized_recordings_are_refused_with_413(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "stt_max_bytes", 4096)
    p = await signup(client)
    r = await send(client, p, WEBM + b"\x00" * 5000)
    assert r.status_code == 413 and r.json()["error"]["code"] == "AUDIO_TOO_LARGE"


@pytest.mark.parametrize("data,ctype", [(b"not audio at all" * 200, "audio/webm"), (WEBM, "text/plain"), (b"\x1aE\xdf\xa3", "audio/webm"), (b"MZ" + b"\x00" * 2048, "audio/webm")])
async def test_anything_that_is_not_real_audio_is_refused_before_it_goes_anywhere(client, _stt, data, ctype):
    p = await signup(client)
    r = await send(client, p, data, ctype)
    assert r.status_code == 422 and r.json()["error"]["code"] == "UNSUPPORTED_AUDIO" and _stt.calls == []


async def test_a_recording_over_ten_minutes_is_refused(client):
    p = await signup(client)
    r = await send(client, p, duration_s="601")
    assert r.status_code == 422 and r.json()["error"]["code"] == "AUDIO_TOO_LONG"


async def test_twenty_an_hour_then_429(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "stt_per_hour", 3)
    p = await signup(client)
    for _ in range(3):
        assert (await send(client, p)).status_code == 200
    r = await send(client, p)
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


@pytest.mark.parametrize("error,status,code", [(ProviderTransientError("x"), 502, "STT_UNAVAILABLE"), (ProviderPermanentError("x"), 502, "STT_MISCONFIGURED")])
async def test_provider_failures_become_friendly_errors(client, error, status, code):
    p = await signup(client)
    set_stt_provider(FakeTranscriber(error=error))
    r = await send(client, p)
    assert r.status_code == status and r.json()["error"]["code"] == code


async def test_it_needs_a_signed_in_user(client):
    r = await client.post(f"{API}/transcriptions", files={"audio": ("rec.webm", WEBM, "audio/webm")})
    assert r.status_code == 401
