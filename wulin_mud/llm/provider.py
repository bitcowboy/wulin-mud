"""LLM provider abstraction.

The whole project sees the LLM through ``LLMProvider.generate(...)``.
Concrete providers live behind this Protocol:

- ``OpenAIProvider`` — production. Async, reads OPENAI_* from the env.
- ``FakeProvider`` — tests. Queues canned responses; records every call
  for assertion.

Choosing the abstraction at this layer (rather than a sprinkling of
``openai.AsyncOpenAI`` calls across the codebase) is what lets PR
diffs cite "no LLM API calls in the diff" with confidence — the
provider is the single seam through which LLMs touch the system.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from openai import AsyncOpenAI


__all__ = [
    "FakeProvider",
    "FakeProviderExhausted",
    "LLMCall",
    "LLMProvider",
    "OpenAIProvider",
]


@dataclass(frozen=True)
class LLMCall:
    """One generation invocation. Recorded by FakeProvider for assertions."""

    system: str
    user: str
    model: str
    temperature: float
    max_tokens: int


class LLMProvider(Protocol):
    """The single seam between wulin-mud and any LLM API.

    Implementations must:
    - Be safe to share across many concurrent action executions.
    - Raise on transport errors (don't swallow). Callers decide retry policy.
    - Be deterministic-by-construction in tests (see FakeProvider).
    """

    async def generate(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> str: ...


# ---------------------------------------------------------------------------
# OpenAI implementation
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """Production provider backed by the official AsyncOpenAI client.

    Configuration is read from environment variables on construction:

    - ``OPENAI_API_KEY`` (required)
    - ``OPENAI_BASE_URL`` (optional, defaults to the SDK default)
    - ``WULIN_MODEL_MEMORY`` (default model for interpretation calls)

    The provider does not implement retries; the OpenAI SDK already
    retries 5xx + rate limits with exponential backoff.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        from openai import AsyncOpenAI

        resolved_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Configure it in .env or pass api_key=... ."
            )
        resolved_base = base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL")
        self._client: AsyncOpenAI = AsyncOpenAI(
            api_key=resolved_key,
            base_url=resolved_base,
        )
        self._default_model = (
            default_model
            if default_model is not None
            else os.environ.get("WULIN_MODEL_MEMORY", "gpt-4o-mini")
        )

    async def generate(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> str:
        chosen_model = model if model is not None else self._default_model
        response = await self._client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        text = choice.message.content
        if text is None:
            raise RuntimeError(
                f"OpenAI returned empty content. finish_reason={choice.finish_reason!r}"
            )
        return text


# ---------------------------------------------------------------------------
# Fake provider for tests
# ---------------------------------------------------------------------------


class FakeProviderExhausted(RuntimeError):
    """Raised when a FakeProvider's response queue is empty and no default is set."""


@dataclass
class FakeProvider:
    """Deterministic provider for tests.

    Construct with one of:

    - ``FakeProvider(default="canned text")`` — every call returns the default
    - ``FakeProvider(responses=["a", "b", "c"])`` — each call pops the next
      response in order; raises FakeProviderExhausted past the end
    - both — queue first, then the default for any extra calls

    The ``calls`` list records every invocation for assertions.
    """

    default: str | None = None
    responses: list[str] = field(default_factory=list)
    calls: list[LLMCall] = field(default_factory=list)

    async def generate(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> str:
        self.calls.append(
            LLMCall(
                system=system,
                user=user,
                model=model or "fake",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
        if self.responses:
            return self.responses.pop(0)
        if self.default is not None:
            return self.default
        raise FakeProviderExhausted("FakeProvider has no more queued responses and no default set.")

    def queue(self, *responses: str) -> None:
        """Append more responses to the queue."""
        self.responses.extend(responses)

    def reset(self) -> None:
        self.responses.clear()
        self.calls.clear()

    @classmethod
    def from_sequence(cls, responses: Sequence[str]) -> FakeProvider:
        return cls(responses=list(responses))
