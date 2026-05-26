"""Talk: the end-to-end LLM dialogue action."""

from __future__ import annotations

from sqlmodel import Session

from tests.actions.conftest import FIXED_NOW, DoAction
from wulin_mud.actions import execute_action
from wulin_mud.core.enums import EventType, InitiatedBy
from wulin_mud.llm import FakeProvider
from wulin_mud.world.persistence import MemoryRow
from wulin_mud.world.state import WorldState

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_talk_returns_llm_reply_via_narrative_hint(
    session: Session, world_seeded: WorldState
) -> None:
    """The LLM's reply ends up in ActionResult.narrative_hint for rendering."""
    llm = FakeProvider(
        responses=[
            "小哥进来坐。",  # dialogue reply
            "这小子，看着年轻。",  # interpretation
        ]
    )
    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "婆婆好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    assert result.narrative_hint == "小哥进来坐。"


async def test_talk_persists_exchange_in_target_memory(
    session: Session, world_seeded: WorldState
) -> None:
    """The target NPC's TALKED memory captures both sides of the turn
    in raw_facts, and the existing interpretation pipeline fills the
    NPC's first-person read of the exchange."""
    llm = FakeProvider(responses=["小哥进来坐。", "这小子第一次来。"])
    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "婆婆好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    # Granny Sun is alone in the room → exactly one Memory row.
    assert len(result.memories_generated) == 1
    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.event_type == EventType.TALKED.value
    assert row.raw_facts["said"] == "婆婆好。"
    assert row.raw_facts["replied"] == "小哥进来坐。"
    # The interpretation was filled by the existing generator.
    assert row.interpretation == "这小子第一次来。"


async def test_talk_bumps_familiarity_smaller_than_greet(
    session: Session, world_seeded: WorldState
) -> None:
    """Talk = 0.02, Greet = 0.05."""
    llm = FakeProvider(default="ok")
    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "你好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    session.expire_all()
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None and sun.player_relationship is not None
    assert abs(sun.player_relationship.familiarity - 0.02) < 1e-9


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


async def test_talk_without_llm_fails_validation(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    """Talk is the one action that cannot run with no LLM."""
    result = await do_action("Talk", {"target_id": "npc_sun_popo", "content": "你好。"}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "LLM" in result.narrative_hint


async def test_talk_empty_content_fails(session: Session, world_seeded: WorldState) -> None:
    llm = FakeProvider(default="ok")
    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "   "},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded is False
    assert result.narrative_hint and "non-empty" in result.narrative_hint


async def test_talk_target_in_different_location_fails(
    session: Session, world_seeded: WorldState
) -> None:
    llm = FakeProvider(default="ok")
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    world_seeded.save_npc(sun.model_copy(update={"current_location_id": "loc_pier"}))
    session.commit()

    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "你好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded is False


async def test_talk_to_yourself_fails(session: Session, world_seeded: WorldState) -> None:
    llm = FakeProvider(default="ok")
    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "嗯。"},
        actor_id="npc_sun_popo",
        initiated_by=InitiatedBy.LLM_DECISION,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded is False
    assert result.narrative_hint and "yourself" in result.narrative_hint


# ---------------------------------------------------------------------------
# Bystanders + memory accounting
# ---------------------------------------------------------------------------


async def test_bystanders_get_thinner_memory(
    session: Session, world_seeded: WorldState, wang_laojiu
) -> None:
    """A third NPC in the room gets a TALKED memory but without the
    transcript — they overheard, not participated."""
    world_seeded.save_npc(wang_laojiu)
    session.commit()

    llm = FakeProvider(
        responses=[
            "小哥进来坐。",  # dialogue
            "我对自己说话的看法",  # target's interpretation
            "他对别人说话的看法",  # bystander's interpretation
        ]
    )
    result = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "婆婆好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert result.succeeded
    assert len(result.memories_generated) == 2

    rows = [session.get(MemoryRow, mid) for mid in result.memories_generated]
    target_row = next(r for r in rows if r is not None and r.npc_id == "npc_sun_popo")
    bystander_row = next(r for r in rows if r is not None and r.npc_id == "npc_wang_laojiu")

    # Target row has the transcript and higher importance.
    assert target_row.raw_facts.get("said") == "婆婆好。"
    assert target_row.importance == 0.3

    # Bystander row has no transcript and is less important.
    assert "said" not in bystander_row.raw_facts
    assert bystander_row.importance == 0.1
    assert "旁观" in bystander_row.tags


# ---------------------------------------------------------------------------
# Multi-turn retrieval — the actual point of the sprint
# ---------------------------------------------------------------------------


async def test_three_turn_conversation_includes_earlier_turns_in_later_prompts(
    session: Session, world_seeded: WorldState
) -> None:
    """Turn 3's prompt must mention turn 1 and turn 2 — proving that
    Memory write + retrieval round-trips through SQLite and lands in
    the next dialogue prompt."""
    llm = FakeProvider(
        responses=[
            # Turn 1 reply, then turn 1's interpretation
            "小哥进来坐。",
            "新来的小子。",
            # Turn 2
            "止血膏八十文。",
            "讲价讲得贼斯文。",
            # Turn 3
            "这事我不方便说。",
            "他怎么开始打听老家的事了。",
        ]
    )

    # Turn 1
    r1 = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "婆婆好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    assert r1.succeeded

    # Turn 2 (slightly later)
    r2 = await execute_action(
        session=session,
        action_name="Talk",
        params={
            "target_id": "npc_sun_popo",
            "content": "止血膏多少文一副？",
        },
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW + 60,
        llm=llm,
    )
    assert r2.succeeded

    # Turn 3 — the one whose prompt we audit
    r3 = await execute_action(
        session=session,
        action_name="Talk",
        params={
            "target_id": "npc_sun_popo",
            "content": "婆婆是哪里人？",
        },
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW + 120,
        llm=llm,
    )
    assert r3.succeeded

    # The third dialogue prompt (calls[4] — every turn makes 2 calls:
    # dialogue then interpretation) should carry both prior interpretations.
    third_dialogue_prompt = llm.calls[4]
    assert third_dialogue_prompt.user.count("婆婆是哪里人") == 1  # current input
    assert "新来的小子" in third_dialogue_prompt.user
    assert "讲价讲得贼斯文" in third_dialogue_prompt.user


async def test_recalled_memories_have_last_recalled_at_bumped(
    session: Session, world_seeded: WorldState
) -> None:
    """A memory used in a dialogue prompt should have last_recalled_at
    set to the time of the prompt — that's what slows its decay."""
    llm = FakeProvider(default="ok")

    # Turn 1 — write a memory that becomes retrievable in turn 2.
    r1 = await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "婆婆好。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=FIXED_NOW,
        llm=llm,
    )
    target_memory_id_t1 = r1.memories_generated[0]
    pre_recall_row = session.get(MemoryRow, target_memory_id_t1)
    assert pre_recall_row is not None
    assert pre_recall_row.last_recalled_at is None

    # Turn 2 — should recall turn 1's memory.
    later_time = FIXED_NOW + 7200
    await execute_action(
        session=session,
        action_name="Talk",
        params={"target_id": "npc_sun_popo", "content": "还在啊。"},
        actor_id="player",
        initiated_by=InitiatedBy.PLAYER_INPUT,
        now=later_time,
        llm=llm,
    )
    session.expire_all()
    post_recall_row = session.get(MemoryRow, target_memory_id_t1)
    assert post_recall_row is not None
    assert post_recall_row.last_recalled_at == later_time
