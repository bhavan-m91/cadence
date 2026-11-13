"""Provider interfaces (PRD 6.2). Core code depends only on these; vendors live in adapters."""

from dataclasses import dataclass, field
from typing import Any, Protocol


class ProviderError(Exception):
    pass


class ProviderTransientError(ProviderError):
    """429, 5xx, timeouts: the job is retried with back-off."""


class ProviderPermanentError(ProviderError):
    """Authentication or request errors: retrying will not help."""


class ProviderOutputError(ProviderError):
    """The model answered but did not call the tool."""


@dataclass
class StructuredRequest:
    system: str
    user: str
    json_schema: dict
    tool_name: str = "record_activities"
    max_tokens: int = 4096
    temperature: float = 0.0
    timeout_s: int = 45
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class StructuredResponse:
    data: dict
    raw: dict
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    model: str
    provider: str


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse: ...
