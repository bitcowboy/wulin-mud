"""Memory ranking is a pure function — tested directly without DB.

Decay over time used to be computed at retrieval; the world tick now
mutates ``importance`` directly (see docs/ontology.md §2.3 and
tests/world/test_decay_memories.py for the tick-side coverage).
What's left here is just the ``importance × tag_relevance`` formula.
"""

from __future__ import annotations

from wulin_mud.core.enums import EventType
from wulin_mud.ontology import Memory
from wulin_mud.world.memory_retrieval import score_memory


def _mem(
    *,
    importance: float,
    tags: tuple[str, ...] = (),
) -> Memory:
    return Memory(
        id="m",
        timestamp=0.0,
        event_type=EventType.MET,
        participants=["a", "b"],
        location_id="loc",
        npc_id="npc_x",
        importance=importance,
        tags=list(tags),
    )


def test_score_equals_importance_with_no_query_tags() -> None:
    """tag_relevance defaults to 1.0 when no query tags are given."""
    m = _mem(importance=0.7)
    assert score_memory(m) == 0.7


def test_full_tag_overlap_keeps_full_score() -> None:
    m = _mem(importance=1.0, tags=("金钱", "砍价"))
    assert score_memory(m, query_tags=("金钱", "砍价")) == 1.0


def test_half_tag_overlap_halves_score() -> None:
    m = _mem(importance=1.0, tags=("金钱", "砍价"))
    assert score_memory(m, query_tags=("金钱", "无关")) == 0.5


def test_no_tag_overlap_zeroes_score() -> None:
    m = _mem(importance=1.0, tags=("金钱",))
    assert score_memory(m, query_tags=("完全无关",)) == 0.0


def test_higher_importance_outranks_lower_at_same_tags() -> None:
    m_low = _mem(importance=0.2)
    m_high = _mem(importance=0.8)
    assert score_memory(m_high) > score_memory(m_low)
