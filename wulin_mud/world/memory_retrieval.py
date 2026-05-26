"""Memory ranking — the function that decides which memories an NPC
brings into a dialogue prompt.

The model is the one in docs/ontology.md §2.3:

    score = importance × recency_factor × tag_relevance

Where:

- ``importance`` is the Memory's own importance field (set when the
  Memory was generated, refined later by the LLM layer).
- ``recency_factor = exp(-decay_rate × elapsed_game_days)`` with
  elapsed measured from ``max(timestamp, last_recalled_at)``. This
  encodes the docs' "被想起的事衰减更慢" rule — if the NPC has
  recalled the event recently, it stays sharp longer.
- ``tag_relevance`` is the fraction of query tags also present on
  the Memory's own tags. Defaults to 1.0 if no query tags are given
  (broad dialogue context retrieval).

All ranking is pure. WorldState methods feed the function rows from
SQLite and apply the ordering; no DB writes happen during scoring.
"""

from __future__ import annotations

import math
from collections.abc import Iterable

from wulin_mud.ontology import Memory

SECONDS_PER_GAME_DAY = 86_400.0
"""How many wall-clock seconds make one game day for decay purposes.

v0.1 keeps game time = real time. A later sprint may rescale (the
roadmap mentions a 1:10 mapping); when it does, this constant moves
into config.
"""


def score_memory(
    memory: Memory,
    *,
    now: float,
    query_tags: Iterable[str] = (),
) -> float:
    """Rank one memory. See module docstring for the formula."""
    last_touched = max(memory.timestamp, memory.last_recalled_at or 0.0)
    elapsed_days = max(0.0, (now - last_touched) / SECONDS_PER_GAME_DAY)
    recency_factor = math.exp(-memory.decay_rate * elapsed_days)

    qtags = set(query_tags)
    if qtags:
        mtags = set(memory.tags)
        overlap = qtags & mtags
        tag_relevance = len(overlap) / len(qtags) if qtags else 1.0
    else:
        tag_relevance = 1.0

    return memory.importance * recency_factor * tag_relevance
