"""REPL fixtures. Same kind of world as tests/actions but with locations
+ items wired up and the Repl object pre-built."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

from wulin_mud.cli.repl import Repl
from wulin_mud.core.enums import Gender, ItemType, LocationType, RelationshipType
from wulin_mud.llm.provider import FakeProvider
from wulin_mud.ontology import (
    NPC,
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


@pytest.fixture
def engine() -> Engine:
    return init_db(db_url="sqlite:///:memory:")


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def llm() -> FakeProvider:
    return FakeProvider(default="(婆婆抬眼看了看。)")


@pytest.fixture
def seeded_world(session: Session) -> Session:
    """Two connected locations, Granny Sun + a teahouse boss, one item."""
    w = WorldState(session)

    pharmacy = Location(
        id="loc_huichun_pharmacy",
        name="回春堂",
        type=LocationType.PHARMACY,
        description="主街中段偏南的药铺。",
        current_npcs=["npc_sun_popo"],
        connected_to=["loc_main_street"],
    )
    main_street = Location(
        id="loc_main_street",
        name="清河主街",
        type=LocationType.STREET,
        description="一条夯土路，贯穿清河镇。",
        connected_to=["loc_huichun_pharmacy", "loc_pier"],
    )
    pier = Location(
        id="loc_pier",
        name="清河码头",
        type=LocationType.PIER,
        description="水陆码头。",
        connected_to=["loc_main_street"],
    )

    sun = NPC(
        id="npc_sun_popo",
        name="孙婆婆",
        age=52,
        gender=Gender.FEMALE,
        role="回春堂老板娘",
        current_location_id="loc_huichun_pharmacy",
        personality=Personality(
            openness=0.4,
            conscientiousness=0.85,
            extraversion=0.45,
            agreeableness=0.55,
            neuroticism=0.65,
            honesty=0.8,
            courage=0.7,
            greed=0.25,
            loyalty=0.9,
            pride=0.6,
        ),
        background="本姓孙",
        speech_style=SpeechStyle(self_reference="我"),
        mood=Mood(valence=0.0, arousal=0.3),
        wealth=500,
    )
    # An item owned by the NPC at the pharmacy.
    zhixue = Item(
        id="item_zhixue_gao",
        name="止血膏",
        type=ItemType.MEDICINE,
        description="疗外伤的膏药。",
        base_price=80,
        owner_id="npc_sun_popo",
        location_id="loc_huichun_pharmacy",
    )
    # Player starts at the pharmacy so most tests don't need a /go first.
    player = PlayerState(current_location_id="loc_huichun_pharmacy", wealth=200)

    w.save_location(pharmacy)
    w.save_location(main_street)
    w.save_location(pier)
    w.save_npc(sun)
    w.save_item(zhixue)
    w.save_player(player)
    session.commit()
    return session


@pytest.fixture
def repl(seeded_world: Session, llm: FakeProvider) -> Repl:
    return Repl(session=seeded_world, llm=llm)


@pytest.fixture
def wang_in_pharmacy(seeded_world: Session) -> Session:
    """Add a second NPC at the pharmacy so multi-NPC tests can disambiguate."""
    w = WorldState(seeded_world)
    wang = NPC(
        id="npc_wang_laojiu",
        name="王老九",
        age=48,
        gender=Gender.MALE,
        role="茶肆掌柜",
        current_location_id="loc_huichun_pharmacy",
        personality=Personality(
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.8,
            agreeableness=0.5,
            neuroticism=0.5,
            honesty=0.5,
            courage=0.5,
            greed=0.5,
            loyalty=0.5,
            pride=0.5,
        ),
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
    w.save_npc(wang)
    seeded_world.commit()
    return seeded_world
