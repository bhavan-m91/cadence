from app.ai.providers.base import (
    LLMProvider,
    ProviderError,
    ProviderOutputError,
    ProviderPermanentError,
    ProviderTransientError,
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
