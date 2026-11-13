"""Anthropic adapter: structured output through a forced tool call."""

import time

import anthropic

from app.ai.providers.base import (
    ProviderOutputError,
    ProviderPermanentError,
    ProviderTransientError,
    StructuredRequest,
    StructuredResponse,
)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str):
        self.model = model
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    async def generate_structured(self, request: StructuredRequest) -> StructuredResponse:
        started = time.perf_counter()
        kwargs = dict(
            model=self.model, max_tokens=request.max_tokens, system=request.system,
            messages=[{"role": "user", "content": request.user}],
            tools=[{"name": request.tool_name, "description": "Record the activities found in the journal entry.", "input_schema": request.json_schema}],
            tool_choice={"type": "tool", "name": request.tool_name}, timeout=request.timeout_s,
        )
        try:
            # No `temperature`: current models fix their own sampling and the SDK rejects the argument.
            resp = await self._client.messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            raise ProviderTransientError(type(e).__name__) from e
        except anthropic.APIStatusError as e:
            if e.status_code in (408, 409, 429) or e.status_code >= 500:  # includes 529 overloaded
                raise ProviderTransientError(f"HTTP {e.status_code}") from e
            raise ProviderPermanentError(f"HTTP {e.status_code}: {getattr(e, 'message', '')[:120]}") from e
        block = next((b for b in resp.content if getattr(b, "type", None) == "tool_use" and b.name == request.tool_name), None)
        if block is None:
            raise ProviderOutputError("no tool call in response")
        return StructuredResponse(
            data=dict(block.input), raw=resp.model_dump(mode="json"), input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens, latency_ms=int((time.perf_counter() - started) * 1000), model=resp.model, provider=self.name)
