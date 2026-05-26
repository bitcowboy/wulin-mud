"""DecayMemories: tick mutates Memory.importance, archives faded ones."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from tests.actions.conftest import FIXED_NOW
from wulin_mud.actions import execute_action
from wulin_mud.core.enums import EventType, InitiatedBy
from wulin_mud.ontology import Memory
from wulin_mud.world.memory_retrieval import ARCHIVED_TAG, IMPORTANCE_FLOOR
from wulin_mud.world.persistence import MemoryRow
from wulin_mud.world.state import WorldState


def _make_memory(
    *,
    mem_id: str,
    importance: float,
    decay_rate: float = 0.5,
    last_recalled_at: float | None = None,
    tags: tuple[str, ...] = (),
) -> Memory:
    return Memory(
        id=mem_id,
        timestamp=FIXED_NOW - 10,
        event_type=EventType.MET,
        participants=["player", "npc_sun_popo"],
        location_id="loc_huichun_pharmacy",
        npc_id="npc_sun_popo",
        importance=importance,
        decay_rate=decay_rate,
        last_recalled_at=last_recalled_at,
        tags=list(tags),
    )


async def test_one_tick_reduces_importance_by_decay_factor(
    session: Session, world_seeded: WorldState
) -> None:
    """importance *= exp(-decay_rate * dt). With dt=1.0 game day,
    decay_rate=0.5: factor = exp(-0.5) ≈ 0.6065."""
    world_seeded.save_memory(_make_memory(mem_id="mem_x", importance=1.0))
    session.commit()

    result = await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": 1.0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded
    session.expire_all()
    row = session.get(MemoryRow, "mem_x")
    assert row is not None
    assert row.importance == pytest.approx(0.6065, abs=1e-3)


async def test_recently_recalled_memory_skips_decay(
    session: Session, world_seeded: WorldState
) -> None:
    """The docs' '被想起的事衰减更慢' rule."""
    # last_recalled_at within the current tick window → protected.
    # tick_dt = 1 game day = 86400 seconds; FIXED_NOW - 30 is well within.
    world_seeded.save_memory(
        _make_memory(
            mem_id="mem_recent",
            importance=1.0,
            last_recalled_at=FIXED_NOW - 30,
        )
    )
    session.commit()

    result = await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": 1.0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded
    session.expire_all()
    row = session.get(MemoryRow, "mem_recent")
    assert row is not None
    assert row.importance == 1.0  # untouched

    stats = result.side_effects_applied[0]
    assert stats["protected_by_recall"] >= 1


async def test_old_recall_does_not_protect(session: Session, world_seeded: WorldState) -> None:
    """A recall from before the tick window doesn't protect."""
    # last_recalled_at older than tick_dt — decays normally.
    world_seeded.save_memory(
        _make_memory(
            mem_id="mem_old_recall",
            importance=1.0,
            last_recalled_at=FIXED_NOW - 86400 * 5,  # 5 game days ago
        )
    )
    session.commit()

    await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": 1.0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    session.expire_all()
    row = session.get(MemoryRow, "mem_old_recall")
    assert row is not None
    assert row.importance < 1.0


async def test_memory_below_floor_gets_archived(session: Session, world_seeded: WorldState) -> None:
    """importance < IMPORTANCE_FLOOR (0.05) → ARCHIVED_TAG added."""
    # importance=0.06, decay 50% per game day, after one tick: 0.06 * 0.6065 ≈ 0.036 < 0.05.
    world_seeded.save_memory(_make_memory(mem_id="mem_dying", importance=0.06))
    session.commit()

    result = await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": 1.0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    session.expire_all()
    row = session.get(MemoryRow, "mem_dying")
    assert row is not None
    assert row.importance < IMPORTANCE_FLOOR
    assert ARCHIVED_TAG in row.tags
    assert result.side_effects_applied[0]["archived"] >= 1


async def test_already_archived_memory_stays_put(
    session: Session, world_seeded: WorldState
) -> None:
    """Archived memories are sticky — they don't shrink further."""
    world_seeded.save_memory(
        _make_memory(mem_id="mem_archived", importance=0.04, tags=(ARCHIVED_TAG,))
    )
    session.commit()

    await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": 1.0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    session.expire_all()
    row = session.get(MemoryRow, "mem_archived")
    assert row is not None
    assert row.importance == pytest.approx(0.04, abs=1e-9)
    # Tag list unchanged
    assert row.tags.count(ARCHIVED_TAG) == 1


async def test_archived_memory_excluded_from_default_retrieval(
    session: Session, world_seeded: WorldState
) -> None:
    """Tagged memories don't surface in default prompts."""
    world_seeded.save_memory(_make_memory(mem_id="mem_active", importance=0.8))
    world_seeded.save_memory(_make_memory(mem_id="mem_dead", importance=0.04, tags=(ARCHIVED_TAG,)))
    session.commit()

    visible = world_seeded.retrieve_relevant_memories("npc_sun_popo")
    ids = {m.id for m in visible}
    assert "mem_active" in ids
    assert "mem_dead" not in ids

    # Forensic flag still surfaces them when explicitly requested.
    all_mems = world_seeded.retrieve_relevant_memories("npc_sun_popo", include_archived=True)
    assert "mem_dead" in {m.id for m in all_mems}


async def test_decay_rejects_negative_dt(session: Session, world_seeded: WorldState) -> None:
    result = await execute_action(
        session=session,
        action_name="DecayMemories",
        params={"tick_dt_game_days": -1.0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded is False
    assert result.narrative_hint and "non-negative" in result.narrative_hint
