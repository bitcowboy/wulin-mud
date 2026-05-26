"""MoveTo: updates location pointers + Location.current_npcs."""

from __future__ import annotations

from sqlmodel import Session

from tests.actions.conftest import DoAction
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.world.state import WorldState


async def test_player_moves_pharmacy_to_pier(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    result = await do_action("MoveTo", {"destination_id": "loc_pier"}, "player")
    assert result.succeeded
    session.expire_all()
    player = world_seeded.get_player()
    assert player is not None
    assert player.current_location_id == "loc_pier"


async def test_npc_move_updates_both_locations_current_npcs(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    pharmacy_before = world_seeded.get_location("loc_huichun_pharmacy")
    assert pharmacy_before is not None
    assert "npc_sun_popo" in pharmacy_before.current_npcs

    result = await do_action(
        "MoveTo",
        {"destination_id": "loc_pier"},
        "npc_sun_popo",
        initiated_by=InitiatedBy.LLM_DECISION,
    )
    assert result.succeeded
    session.expire_all()
    pharmacy_after = world_seeded.get_location("loc_huichun_pharmacy")
    pier_after = world_seeded.get_location("loc_pier")
    assert pharmacy_after is not None and pier_after is not None
    assert "npc_sun_popo" not in pharmacy_after.current_npcs
    assert "npc_sun_popo" in pier_after.current_npcs

    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    assert sun.current_location_id == "loc_pier"


async def test_move_to_disconnected_destination_fails(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    from wulin_mud.core.enums import LocationType
    from wulin_mud.ontology import Location

    world_seeded.save_location(
        Location(
            id="loc_far_away",
            name="远地",
            type=LocationType.OTHER,
            description="not connected to anything",
        )
    )
    session.commit()

    result = await do_action("MoveTo", {"destination_id": "loc_far_away"}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "not connected" in result.narrative_hint


async def test_move_to_same_location_fails(do_action: DoAction, world_seeded: WorldState) -> None:
    result = await do_action("MoveTo", {"destination_id": "loc_huichun_pharmacy"}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "already at destination" in result.narrative_hint


async def test_move_does_not_generate_memories(
    do_action: DoAction, world_seeded: WorldState
) -> None:
    """v0.1 decision: movement is too noisy to record per-witness."""
    result = await do_action("MoveTo", {"destination_id": "loc_pier"}, "player")
    assert result.succeeded
    assert result.memories_generated == []
