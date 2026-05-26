"""LLM integration layer.

See docs/llm-integration.md for the design spec.

Public surface:

- ``LLMProvider`` (Protocol) — the single seam between wulin-mud and any LLM.
- ``OpenAIProvider`` — production implementation backed by AsyncOpenAI.
- ``FakeProvider`` — deterministic provider for tests.
- ``generate_interpretation`` — high-level: take a Memory + NPC context,
  return the NPC's first-person reading of the event.
"""

from wulin_mud.llm.dialogue import generate_dialogue
from wulin_mud.llm.interpretation import generate_interpretation
from wulin_mud.llm.provider import (
    FakeProvider,
    FakeProviderExhausted,
    LLMCall,
    LLMProvider,
    OpenAIProvider,
)

__all__ = [
    "FakeProvider",
    "FakeProviderExhausted",
    "LLMCall",
    "LLMProvider",
    "OpenAIProvider",
    "generate_dialogue",
    "generate_interpretation",
]
