"""Memory ranking is a pure function — tested directly without DB."""

from __future__ import annotations

from wulin_mud.core.enums import EventType
from wulin_mud.ontology import Memory
from wulin_mud.world.memory_retrieval import SECONDS_PER_GAME_DAY, score_memory


def _mem(
    *,
    importance: float,
    timestamp: float = 0.0,
    decay_rate: float = 0.05,
    last_recalled_at: float | None = None,
    tags: tuple[str, ...] = (),
) -> Memory:
    return Memory(
        id="m",
        timestamp=timestamp,
        event_type=EventType.MET,
        participants=["a", "b"],
        location_id="loc",
        npc_id="npc_x",
        importance=importance,
        decay_rate=decay_rate,
        last_recalled_at=last_recalled_at,
        tags=list(tags),
    )


def test_fresh_memory_score_equals_importance() -> None:
    """When elapsed_days = 0, recency_factor = 1.0 → score = importance."""
    m = _mem(importance=0.7, timestamp=1000.0)
    assert score_memory(m, now=1000.0) == 0.7


def test_decay_shrinks_score_over_game_days() -> None:
    m = _mem(importance=1.0, timestamp=0.0, decay_rate=0.5)
    a_day_later = score_memory(m, now=SECONDS_PER_GAME_DAY)
    # exp(-0.5) ≈ 0.6065
    assert 0.6 < a_day_later < 0.62


def test_recall_bumps_effective_freshness() -> None:
    """If last_recalled_at is recent, the memory should decay from there,
    not from the original timestamp."""
    m_no_recall = _mem(importance=1.0, timestamp=0.0, decay_rate=0.5)
    m_recalled = _mem(
        importance=1.0,
        timestamp=0.0,
        decay_rate=0.5,
        last_recalled_at=SECONDS_PER_GAME_DAY * 0.5,
    )
    now = SECONDS_PER_GAME_DAY
    s_a = score_memory(m_no_recall, now=now)
    s_b = score_memory(m_recalled, now=now)
    assert s_b > s_a, "recalled memory should score higher than never-recalled at same age"


def test_query_tag_overlap_scales_score() -> None:
    m = _mem(importance=1.0, timestamp=0.0, tags=("金钱", "砍价"))
    full_overlap = score_memory(m, now=0.0, query_tags=("金钱", "砍价"))
    half_overlap = score_memory(m, now=0.0, query_tags=("金钱", "无关"))
    no_overlap = score_memory(m, now=0.0, query_tags=("完全无关",))
    no_query = score_memory(m, now=0.0)
    assert full_overlap == 1.0
    assert half_overlap == 0.5
    assert no_overlap == 0.0
    # Empty query → full credit on tag axis.
    assert no_query == 1.0


def test_higher_importance_always_outranks_when_age_equal() -> None:
    m_low = _mem(importance=0.2, timestamp=0.0)
    m_high = _mem(importance=0.8, timestamp=0.0)
    now = SECONDS_PER_GAME_DAY * 2  # both at same age
    assert score_memory(m_high, now=now) > score_memory(m_low, now=now)
