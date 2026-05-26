"""OffendNPC: affection drops, mood sours, negative-charge Memory."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from tests.actions.conftest import DoAction
from wulin_mud.core.enums import EventType, InitiatedBy
from wulin_mud.world.persistence import MemoryRow
from wulin_mud.world.state import WorldState


async def test_player_offends_sun_drops_affection_mood_and_trust(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    sun_before = world_seeded.get_npc("npc_sun_popo")
    assert sun_before is not None
    valence_before = sun_before.mood.valence

    result = await do_action(
        "OffendNPC",
        {"target_id": "npc_sun_popo", "description": "嘲讽她的医术"},
        "player",
    )
    assert result.succeeded

    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None
    assert sun_after.player_relationship is not None
    # v2 magnitudes — offense actually registers in dialogue.
    assert sun_after.player_relationship.affection == pytest.approx(-0.30)
    # trust was 0 to begin with (no prior PlayerRelationship), clamps at 0
    assert sun_after.player_relationship.trust == 0.0
    assert sun_after.mood.valence == pytest.approx(valence_before - 0.20)


async def test_offend_with_prior_trust_drops_trust(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    """Trust drops even when there's already a PlayerRelationship on file."""
    from wulin_mud.core.enums import RelationshipType
    from wulin_mud.ontology import PlayerRelationship

    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    sun.player_relationship = PlayerRelationship(
        other_id="player",
        affection=0.2,
        trust=0.5,
        familiarity=0.6,
        relationship_type=RelationshipType.STRANGER,
        relationship_label="外人",
    )
    world_seeded.save_npc(sun)
    session.commit()

    await do_action("OffendNPC", {"target_id": "npc_sun_popo"}, "player")
    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None and sun_after.player_relationship is not None
    assert sun_after.player_relationship.trust == pytest.approx(0.40)  # 0.5 − 0.1
    assert sun_after.player_relationship.affection == pytest.approx(-0.10)  # 0.2 − 0.3


async def test_offend_generates_high_importance_negative_memory(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    result = await do_action(
        "OffendNPC",
        {"target_id": "npc_sun_popo", "description": "嘲讽她的医术"},
        "player",
    )
    assert result.succeeded
    assert len(result.memories_generated) == 1
    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.event_type == EventType.OFFENDED.value
    assert row.importance == pytest.approx(0.6)
    assert row.emotional_charge == pytest.approx(-0.4)
    assert row.raw_facts["description"] == "嘲讽她的医术"
    assert row.interpretation == ""  # LLM will fill this later


async def test_offend_affection_floors_at_minus_one(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    from wulin_mud.core.enums import RelationshipType
    from wulin_mud.ontology import PlayerRelationship

    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    sun.player_relationship = PlayerRelationship(
        other_id="player",
        affection=-0.95,
        trust=0.0,
        familiarity=0.5,
        relationship_type=RelationshipType.STRANGER,
        relationship_label="外人",
    )
    world_seeded.save_npc(sun)
    session.commit()

    result = await do_action("OffendNPC", {"target_id": "npc_sun_popo"}, "player")
    assert result.succeeded
    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None and sun_after.player_relationship is not None
    assert sun_after.player_relationship.affection == -1.0  # clamped


async def test_offending_self_fails(do_action: DoAction, world_seeded: WorldState) -> None:
    result = await do_action(
        "OffendNPC",
        {"target_id": "npc_sun_popo"},
        "npc_sun_popo",
        initiated_by=InitiatedBy.LLM_DECISION,
    )
    assert result.succeeded is False
    assert result.narrative_hint and "yourself" in result.narrative_hint
