"""Thin wrapper over the Anthropic SDK, same idea as mailer.py: the rest of the
app talks to LLMClient and never imports the SDK. Responses come back as small
dataclasses so the agent loop can be tested with a scripted fake."""

import logging
from dataclasses import dataclass, field
from typing import Any

import anthropic

from app.infra.config import settings

logger = logging.getLogger(__name__)

# on a safety decline the API re-runs the request on Anthropic's recommended
# fallback model instead of returning the refusal
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LLMResponse:
    stop_reason: str | None
    text: str
    tool_calls: list[ToolCall]
    # raw blocks, sent back unchanged as the assistant turn (thinking included)
    content: list[Any] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)


class LLMClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int,
        effort: str,
        timeout: float,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self._client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

    async def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {}
        if tools:
            kwargs["tools"] = tools

        try:
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=messages,  # type: ignore[arg-type]
                output_config={"effort": self.effort},  # type: ignore[typeddict-item]
                betas=[_FALLBACK_BETA],
                fallbacks="default",
                **kwargs,
            )
        except anthropic.APIStatusError as exc:
            logger.error(
                "LLM request failed",
                extra={
                    "status_code": exc.status_code,
                    "llm_request_id": exc.request_id,
                    "exception": type(exc).__name__,
                },
            )
            raise LLMError("LLM request failed") from exc
        except anthropic.APIConnectionError as exc:
            logger.error(
                "LLM unreachable",
                extra={"exception": type(exc).__name__},
            )
            raise LLMError("LLM unreachable") from exc

        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=dict(b.input))  # type: ignore[union-attr]
            for b in response.content
            if b.type == "tool_use"
        ]

        return LLMResponse(
            stop_reason=response.stop_reason,
            text=text.strip(),
            tool_calls=tool_calls,
            content=list(response.content),
            usage=LLMUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Built on first use so the app starts without a key; a missing key only
    fails the assistant, as an LLMError the caller already handles."""
    global _client

    if _client is None:
        if not settings.ANTHROPIC_API_KEY:
            raise LLMError("ANTHROPIC_API_KEY is not configured")
        _client = LLMClient(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.LLM_MODEL,
            max_tokens=settings.LLM_MAX_TOKENS,
            effort=settings.LLM_EFFORT,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )

    return _client
