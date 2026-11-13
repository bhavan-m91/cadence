from app.ai.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderOutputError,
    ProviderPermanentError,
    ProviderTransientError,
    SpeechToTextProvider,
    StructuredRequest,
    StructuredResponse,
)
from app.core.config import get_settings

_override: LLMProvider | None = None
_cached: LLMProvider | None = None


def set_provider(p: LLMProvider | None) -> None:
    """Tests and the eval harness inject a provider here."""
    global _override
    _override = p


def provider_name() -> str:
    s = get_settings()
    if s.llm_provider == "fake" or (s.llm_provider == "auto" and not s.anthropic_api_key):
        return "fake"
    return "anthropic"


def get_llm_provider() -> LLMProvider:
    global _cached
    if _override is not None:
        return _override
    if _cached is None:
        s = get_settings()
        if provider_name() == "anthropic":
            from app.ai.providers.anthropic_provider import AnthropicProvider

            _cached = AnthropicProvider(s.anthropic_api_key, s.llm_model_extract)
        else:
            from app.ai.providers.fake_provider import FakeProvider

            _cached = FakeProvider()
    return _cached


def provider_status() -> dict:
    p = get_llm_provider()
    return {"provider": p.name, "model": p.model, "demo": p.name in ("fake", "fixture")}


__all__ = ["LLMProvider", "ProviderError", "ProviderOutputError", "ProviderPermanentError", "ProviderTransientError", "StructuredRequest",
           "StructuredResponse", "get_llm_provider", "provider_status", "set_provider"]


# ---- speech-to-text (FR-016). Unlike the LLM there is no offline stand-in: invented text from a "demo" transcriber would look real.
_stt_override: SpeechToTextProvider | None = None


def set_stt_provider(p: SpeechToTextProvider | None) -> None:
    global _stt_override
    _stt_override = p


def get_stt_provider() -> SpeechToTextProvider | None:
    if _stt_override is not None:
        return _stt_override
    s = get_settings()
    if s.stt_provider == "fake" and not s.is_production:
        from app.ai.providers.stt_fake import FakeTranscriber

        return FakeTranscriber()
    if s.stt_provider in ("auto", "openai") and s.openai_api_key:
        from app.ai.providers.stt_openai import OpenAITranscriber

        return OpenAITranscriber(s.openai_api_key, s.stt_model)
    return None


def stt_status() -> dict:
    p = get_stt_provider()
    return {"stt_available": p is not None, "stt_provider": p.name if p else None}
