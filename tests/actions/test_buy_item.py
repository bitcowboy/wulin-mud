"""BuyItem: ownership transfer + wealth move + Memory."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from tests.actions.conftest import DoAction
from wulin_mud.core.enums import EventType
from wulin_mud.world.state import WorldState


async def test_player_buys_item_at_base_price(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 80}, "player")
    assert result.succeeded
    session.expire_all()

    player = world_seeded.get_player()
    assert player is not None
    assert player.wealth == 120  # 200 - 80
    assert "item_zhixue_gao" in player.inventory_item_ids

    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    assert sun.wealth == 580  # 500 + 80

    item = world_seeded.get_item("item_zhixue_gao")
    assert item is not None
    assert item.owner_id == "player"
    assert item.location_id is None  # now carried, not shelved


async def test_player_haggled_price_50_works(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    """Within 2× of base_price is acceptable; 50 < 80 is fine."""
    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 50}, "player")
    assert result.succeeded
    session.expire_all()
    player = world_seeded.get_player()
    assert player is not None
    assert player.wealth == 150


async def test_price_above_2x_base_fails(do_action: DoAction, world_seeded: WorldState) -> None:
    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 200}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "exceeds 2x" in result.narrative_hint


async def test_insufficient_funds_fails(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    player = world_seeded.get_player()
    assert player is not None
    world_seeded.save_player(player.model_copy(update={"wealth": 10}))
    session.commit()

    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 50}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "insufficient" in result.narrative_hint


async def test_vendor_in_different_location_fails(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    world_seeded.save_npc(sun.model_copy(update={"current_location_id": "loc_pier"}))
    session.commit()

    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 80}, "player")
    assert result.succeeded is False


async def test_buy_writes_witness_memory_with_raw_facts(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 75}, "player")
    assert result.succeeded
    # Granny Sun is the only NPC in the room → exactly one Memory row.
    assert len(result.memories_generated) == 1
    from wulin_mud.world.persistence import MemoryRow

    row = session.get(MemoryRow, result.memories_generated[0])
    assert row is not None
    assert row.event_type == EventType.BOUGHT.value
    assert row.npc_id == "npc_sun_popo"
    assert row.raw_facts["price"] == 75
    assert row.raw_facts["base_price"] == 80
    assert row.importance == pytest.approx(0.3)


async def test_buying_your_own_item_fails(
    do_action: DoAction, session: Session, world_seeded: WorldState
) -> None:
    item = world_seeded.get_item("item_zhixue_gao")
    assert item is not None
    world_seeded.save_item(item.model_copy(update={"owner_id": "player"}))
    session.commit()

    result = await do_action("BuyItem", {"item_id": "item_zhixue_gao", "price": 80}, "player")
    assert result.succeeded is False
    assert result.narrative_hint and "already own" in result.narrative_hint
