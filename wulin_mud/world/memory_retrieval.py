"""Memory ranking + tick-time constants.

Model (per docs/ontology.md §2.3):

    score = importance × tag_relevance

``importance`` is the source of truth for "how relevant is this memory
right now". It starts at the value set when the Memory was generated
and **shrinks over time** — but the shrinking is done by the world
tick (``DecayMemories``), not lazily at retrieval. That separation
matters: it means a Memory's relevance is the same value whether you
score it once or a hundred times, and a memory that's been "forgotten"
(importance below :data:`IMPORTANCE_FLOOR`) is materially archived in
the DB rather than ranking-low-in-pure-functions.

``tag_relevance`` is the fraction of query tags also present on the
memory's own tags. Defaults to 1.0 with no query (broad context
retrieval).

Recall mechanics live on the tick side too: when a memory is used in a
prompt, :meth:`WorldState.mark_memories_recalled` bumps its
``last_recalled_at``. The next DecayMemories tick skips memories
recalled within its window — that's the docs' "被想起的事衰减更慢"
rule.
"""

from __future__ import annotations

from collections.abc import Iterable

from wulin_mud.ontology import Memory

SECONDS_PER_GAME_DAY = 86_400.0
"""Wall-clock seconds in one game day.

v0.1 treats game time = real time. ``WULIN_TIME_RATIO`` from .env
makes this configurable; see :mod:`wulin_mud.world.tick`.
"""

IMPORTANCE_FLOOR = 0.05
"""Below this, a memory is archived: tagged :data:`ARCHIVED_TAG`,
excluded from default retrieval, but kept in the DB for forensics."""

ARCHIVED_TAG = "archived"
"""Sentinel tag applied to memories whose importance has decayed below
:data:`IMPORTANCE_FLOOR`. Retrieval skips memories carrying this tag."""


def score_memory(
    memory: Memory,
    *,
    query_tags: Iterable[str] = (),
) -> float:
    """Rank one memory. score = importance × tag_relevance."""
    qtags = set(query_tags)
    if qtags:
        mtags = set(memory.tags)
        overlap = qtags & mtags
        tag_relevance = len(overlap) / len(qtags)
    else:
        tag_relevance = 1.0

    return memory.importance * tag_relevance
