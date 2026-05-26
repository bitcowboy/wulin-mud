"""Greet: bumps familiarity, generates one Memory per witness, audits."""

from __future__ import annotations

import pytest
from sqlmodel import Session, select

from tests.actions.conftest import FIXED_NOW, DoAction
from wulin_mud.core.enums import EventType, InitiatedBy
from wulin_mud.world.persistence import MemoryRow
from wulin_mud.world.state import WorldState


async def test_player_greets_sun_creates_first_meeting_relationship(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    """First Greet sets up a fresh PlayerRelationship from scratch."""
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    assert sun.player_relationship is None  # not seeded yet

    result = await do_action("Greet", {"target_id": "npc_sun_popo"}, "player")
    assert result.succeeded

    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None
    assert sun_after.player_relationship is not None
    assert sun_after.player_relationship.familiarity == pytest.approx(0.05)
    assert sun_after.player_relationship.first_met_at == FIXED_NOW


async def test_repeated_greet_keeps_bumping_familiarity(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    for _ in range(3):
        result = await do_action("Greet", {"target_id": "npc_sun_popo"}, "player")
        assert result.succeeded
    session.expire_all()
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None and sun.player_relationship is not None
    assert sun.player_relationship.familiarity == pytest.approx(0.15)


async def test_familiarity_caps_at_one(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    from wulin_mud.core.enums import RelationshipType
    from wulin_mud.ontology import PlayerRelationship

    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    sun.player_relationship = PlayerRelationship(
        other_id="player",
        affection=0.0,
        trust=0.0,
        familiarity=0.98,
        relationship_type=RelationshipType.STRANGER,
        relationship_label="外人",
        first_met_at=900.0,
    )
    world_seeded.save_npc(sun)
    session.commit()

    result = await do_action("Greet", {"target_id": "npc_sun_popo"}, "player")
    assert result.succeeded
    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None and sun_after.player_relationship is not None
    assert sun_after.player_relationship.familiarity == 1.0


async def test_greet_generates_one_memory_per_witness(
    do_action: DoAction, session: Session, world_seeded: WorldState, wang_laojiu
) -> None:
    """With two NPCs in the room, Greet should drop two Memory rows."""
    world_seeded.save_npc(wang_laojiu)
    session.commit()

    result = await do_action("Greet", {"target_id": "npc_sun_popo"}, "player")
    assert result.succeeded
    assert len(result.memories_generated) == 2

    rows = session.exec(
        select(MemoryRow).where(MemoryRow.id.in_(result.memories_generated))  # type: ignore[attr-defined]
    ).all()
    assert {r.npc_id for r in rows} == {"npc_sun_popo", "npc_wang_laojiu"}
    for row in rows:
        assert row.event_type == EventType.MET.value
        assert row.interpretation == ""  # LLM fills this later
        assert row.importance == pytest.approx(0.15)
        assert "招呼" in row.tags


async def test_greet_self_fails_validation(do_action: DoAction, world_seeded: WorldState) -> None:
    result = await do_action("Greet", {"target_id": "player"}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "yourself" in result.narrative_hint


async def test_greet_target_in_different_location_fails(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    world_seeded.save_npc(sun.model_copy(update={"current_location_id": "loc_pier"}))
    session.commit()

    result = await do_action("Greet", {"target_id": "npc_sun_popo"}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "loc_pier" in result.narrative_hint


async def test_npc_greets_other_npc_creates_relationship_stub(
    do_action: DoAction, session: Session, world_seeded: WorldState, wang_laojiu
) -> None:
    """NPC→NPC greet with no prior relationship creates a STRANGER stub
    and bumps its familiarity."""
    world_seeded.save_npc(wang_laojiu)
    session.commit()

    result = await do_action(
        "Greet",
        {"target_id": "npc_sun_popo"},
        "npc_wang_laojiu",
        initiated_by=InitiatedBy.LLM_DECISION,
    )
    assert result.succeeded
    session.expire_all()
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    assert "npc_wang_laojiu" in sun.relationships
    assert sun.relationships["npc_wang_laojiu"].familiarity == pytest.approx(0.05)
