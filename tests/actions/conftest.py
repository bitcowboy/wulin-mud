"""Shared fixtures for action-layer tests.

Each test gets a fresh in-memory SQLite + a tiny seeded world:
- Two connected locations: pharmacy ↔ pier
- Granny Sun (npc_sun_popo) at the pharmacy
- One vendor item owned by Granny Sun
- A player at the pharmacy with some wealth

This keeps every action test small and self-contained.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

from wulin_mud.actions import execute_action
from wulin_mud.actions.base import ActionResult
from wulin_mud.core.enums import Gender, InitiatedBy, ItemType, LocationType, RelationshipType
from wulin_mud.ontology import (
    NPC,
    PLAYER_ID,
    Item,
    Location,
    Mood,
    Personality,
    PlayerState,
    Relationship,
    SpeechStyle,
)
from wulin_mud.world.persistence import init_db
from wulin_mud.world.state import WorldState

DoAction = Callable[..., Awaitable[ActionResult]]


# ---------------------------------------------------------------------------
# Engine + session
# ---------------------------------------------------------------------------


@pytest.fixture
def engine() -> Engine:
    return init_db(db_url="sqlite:///:memory:")


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


FIXED_NOW = 1000.0


@pytest.fixture
def world(session: Session) -> WorldState:
    return WorldState(session, now=FIXED_NOW)


@pytest.fixture
def do_action(session: Session) -> DoAction:
    """Bind execute_action to the test's session and the FIXED_NOW clock.

    Tests can call ``await do_action("Greet", {...}, "player")`` and let
    every action see the same deterministic timestamp.
    """

    async def _do(
        action_name: str,
        params: dict[str, Any],
        actor_id: str,
        *,
        initiated_by: InitiatedBy = InitiatedBy.PLAYER_INPUT,
        llm_reasoning: str | None = None,
        now: float = FIXED_NOW,
    ) -> ActionResult:
        return await execute_action(
            session=session,
            action_name=action_name,
            params=params,
            actor_id=actor_id,
            initiated_by=initiated_by,
            llm_reasoning=llm_reasoning,
            now=now,
        )

    return _do


# ---------------------------------------------------------------------------
# Seed data: locations, NPCs, player, items
# ---------------------------------------------------------------------------


def _personality(**overrides: float) -> Personality:
    base = {
        "openness": 0.5,
        "conscientiousness": 0.5,
        "extraversion": 0.5,
        "agreeableness": 0.5,
        "neuroticism": 0.5,
        "honesty": 0.5,
        "courage": 0.5,
        "greed": 0.5,
        "loyalty": 0.5,
        "pride": 0.5,
    }
    base.update(overrides)
    return Personality(**base)


@pytest.fixture
def pharmacy() -> Location:
    return Location(
        id="loc_huichun_pharmacy",
        name="回春堂",
        type=LocationType.PHARMACY,
        description="主街中段偏南的药铺",
        connected_to=["loc_pier"],
    )


@pytest.fixture
def pier() -> Location:
    return Location(
        id="loc_pier",
        name="清河码头",
        type=LocationType.PIER,
        description="镇东头的水陆码头",
        connected_to=["loc_huichun_pharmacy"],
    )


@pytest.fixture
def sun_popo() -> NPC:
    return NPC(
        id="npc_sun_popo",
        name="孙婆婆",
        age=52,
        gender=Gender.FEMALE,
        role="回春堂老板娘",
        current_location_id="loc_huichun_pharmacy",
        personality=_personality(conscientiousness=0.85, pride=0.6),
        background="本姓孙",
        speech_style=SpeechStyle(self_reference="我"),
        mood=Mood(valence=0.0, arousal=0.3),
        wealth=500,
    )


@pytest.fixture
def wang_laojiu() -> NPC:
    """Second NPC at the same location — used to exercise witness sets > 1."""
    return NPC(
        id="npc_wang_laojiu",
        name="王老九",
        age=48,
        gender=Gender.MALE,
        role="茶肆掌柜",
        current_location_id="loc_huichun_pharmacy",
        personality=_personality(extraversion=0.8),
        background="茶肆开了二十年",
        relationships={
            "npc_sun_popo": Relationship(
                other_id="npc_sun_popo",
                affection=0.4,
                trust=0.5,
                familiarity=0.9,
                relationship_type=RelationshipType.OLD_ACQUAINTANCE,
                relationship_label="旧识",
            ),
        },
    )


@pytest.fixture
def item_zhixue_gao() -> Item:
    return Item(
        id="item_zhixue_gao",
        name="止血膏",
        type=ItemType.MEDICINE,
        description="疗外伤的膏药",
        base_price=80,
        owner_id="npc_sun_popo",
        location_id="loc_huichun_pharmacy",
    )


@pytest.fixture
def player_at_pharmacy() -> PlayerState:
    return PlayerState(
        current_location_id="loc_huichun_pharmacy",
        wealth=200,
        inventory_item_ids=[],
    )


@pytest.fixture
def world_seeded(
    session: Session,
    world: WorldState,
    pharmacy: Location,
    pier: Location,
    sun_popo: NPC,
    item_zhixue_gao: Item,
    player_at_pharmacy: PlayerState,
) -> WorldState:
    """A minimal world: 2 locations, Granny Sun at the pharmacy, one item
    for sale, and a player co-located with her."""
    # Cross-reference sun_popo into the pharmacy's current_npcs
    pharmacy = pharmacy.model_copy(update={"current_npcs": [sun_popo.id]})

    world.save_location(pharmacy)
    world.save_location(pier)
    world.save_npc(sun_popo)
    world.save_item(item_zhixue_gao)
    world.save_player(player_at_pharmacy)
    session.commit()
    return world


__all__ = ["PLAYER_ID"]
