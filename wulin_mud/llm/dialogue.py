"""High-level helper: turn (NPC, player_input, context) into a reply.

Dialogue uses a higher temperature than interpretation — we want the
NPC to feel alive, not mechanical. The persona itself is what keeps the
output consistent across turns; the temperature can be reasonably warm
without breaking character (the system prompt enforces the bounds).
"""

from __future__ import annotations

import os
from collections.abc import Sequence

from wulin_mud.llm.prompts.dialogue import build_dialogue_prompt
from wulin_mud.llm.provider import LLMProvider
from wulin_mud.ontology import NPC, Memory

# Roomy: 3 sentences of Chinese can be ~120 tokens, plus a stage-direction
# parenthetical. 500 leaves plenty of headroom without inviting essays.
_DEFAULT_MAX_TOKENS = 500
# Warmer than interpretation. Personas + the section-headed prompt provide
# the anti-drift bounds; temperature controls phrasing variety.
_DEFAULT_TEMPERATURE = 0.7


async def generate_dialogue(
    *,
    provider: LLMProvider,
    npc: NPC,
    actor_id: str,
    player_input: str,
    relevant_memories: Sequence[Memory] = (),
    recent_dialogue: Sequence[Memory] = (),
    model: str | None = None,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> str:
    """Return the NPC's reply to ``player_input``.

    ``model`` defaults to ``WULIN_MODEL_DIALOGUE`` env var if set;
    otherwise whatever the provider's default is.
    """
    prompt = build_dialogue_prompt(
        npc=npc,
        actor_id=actor_id,
        player_input=player_input,
        relevant_memories=relevant_memories,
        recent_dialogue=recent_dialogue,
    )
    chosen_model = model if model is not None else os.environ.get("WULIN_MODEL_DIALOGUE")
    raw = await provider.generate(
        system=prompt.system,
        user=prompt.user,
        model=chosen_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return raw.strip()
