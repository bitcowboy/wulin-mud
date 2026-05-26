"""High-level helper: turn ``(witness NPC, event Memory)`` into the NPC's
first-person interpretation string.

This is the single function callers (WorldState.record_witnessed_event,
soon) invoke. It pulls together the prompt builder + the provider call;
the rest of the system never sees the prompt strings.
"""

from __future__ import annotations

import os

from wulin_mud.llm.prompts.interpretation import build_interpretation_prompt
from wulin_mud.llm.provider import LLMProvider
from wulin_mud.ontology import NPC, Memory

# Interpretations are short by design — half a line of inner monologue.
# 200 tokens is plenty and caps cost on the high-frequency path.
_DEFAULT_MAX_TOKENS = 200
# Lower than dialogue: we want the NPC's *characteristic* read, not a
# creative one.
_DEFAULT_TEMPERATURE = 0.5


async def generate_interpretation(
    *,
    provider: LLMProvider,
    npc: NPC,
    memory: Memory,
    actor_id: str,
    model: str | None = None,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> str:
    """Generate the NPC's first-person reading of ``memory``.

    Returns a single short string ready to be assigned to
    ``memory.interpretation``. Caller is responsible for the actual
    assignment + persistence; we don't mutate the Memory here so the
    function stays a pure-ish translator.

    ``model`` defaults to the value of ``WULIN_MODEL_MEMORY`` if the
    caller doesn't override (provider may still apply its own default
    if env var is unset).
    """
    prompt = build_interpretation_prompt(npc=npc, memory=memory, actor_id=actor_id)
    chosen_model = model if model is not None else os.environ.get("WULIN_MODEL_MEMORY")
    raw = await provider.generate(
        system=prompt.system,
        user=prompt.user,
        model=chosen_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return raw.strip()
