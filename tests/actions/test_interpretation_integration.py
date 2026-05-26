"""When an action runs with an LLM provider, the Memory rows it emits
have their interpretation field filled. When the provider is absent
they stay empty (test convenience)."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from tests.actions.conftest import FIXED_NOW
from wulin_mud.actions import execute_action
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.llm import FakeProvider
from wulin_mud.world.persistence import MemoryRow
from wulin_mud.world.state import WorldState


async def test_greet_with_llm_fills_interpretation(
    session: Session, world_seeded: WorldState
) -> None:
    llm = FakeProvider(default="这小子第一次来，看着年轻。")

    result = await execute_action(
        session=session,
        action_name="Greet",
        params={"target_id": "npc_sun_popo"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    assert len(result.memories_generated) == 1

    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.interpretation == "这小子第一次来，看着年轻。"
    # One LLM call was made (one witness).
    assert len(llm.calls) == 1


async def test_buy_item_with_llm_fills_interpretation(
    session: Session, world_seeded: WorldState
) -> None:
    llm = FakeProvider(default="这小子也算痛快。")
    result = await execute_action(
        session=session,
        action_name="BuyItem",
        params={"item_id": "item_zhixue_gao", "price": 80},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.interpretation == "这小子也算痛快。"


async def test_offend_with_llm_fills_interpretation(
    session: Session, world_seeded: WorldState
) -> None:
    llm = FakeProvider(default="这小子没规矩。")
    result = await execute_action(
        session=session,
        action_name="OffendNPC",
        params={"target_id": "npc_sun_popo", "description": "嘲讽她的医术"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.interpretation == "这小子没规矩。"


async def test_multiple_witnesses_one_llm_call_per_witness(
    session: Session, world_seeded: WorldState, wang_laojiu
) -> None:
    """Two NPCs in the room → two Memory rows → two LLM calls, each with
    different interpretations."""
    world_seeded.save_npc(wang_laojiu)
    session.commit()

    llm = FakeProvider(responses=["第一个解读", "第二个解读"])
    result = await execute_action(
        session=session,
        action_name="Greet",
        params={"target_id": "npc_sun_popo"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    assert len(result.memories_generated) == 2
    assert len(llm.calls) == 2

    interpretations = sorted(
        session.get(MemoryRow, mid).interpretation  # type: ignore[union-attr]
        for mid in result.memories_generated
    )
    assert interpretations == ["第一个解读", "第二个解读"]


async def test_without_llm_interpretations_remain_empty(
    session: Session, world_seeded: WorldState
) -> None:
    """Backward-compat: no provider → no interpretation. Existing tests
    that don't care about LLM keep passing."""
    result = await execute_action(
        session=session,
        action_name="Greet",
        params={"target_id": "npc_sun_popo"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        # llm=None  (default)
    )
    assert result.succeeded
    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.interpretation == ""


async def test_filled_interpretation_is_locked_by_writeonce_invariant(
    session: Session, world_seeded: WorldState
) -> None:
    """The whole point of generating-at-event-time. Once the LLM has
    filled it, a later attempt to overwrite via raw SQL must be blocked
    by the trigger from PR #1."""
    llm = FakeProvider(default="这小子，没规矩。")
    result = await execute_action(
        session=session,
        action_name="Greet",
        params={"target_id": "npc_sun_popo"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    mem_id = result.memories_generated[0]

    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    engine = session.get_bind()
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:  # type: ignore[union-attr]
            conn.execute(
                text("UPDATE memories SET interpretation = :v WHERE id = :id"),
                {"v": "the LLM was wrong, retry", "id": mem_id},
            )
    assert "write-once" in str(exc.value)
