"""Shared fixtures: in-memory engines and Object-Type factories."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

from wulin_mud.core.enums import (
    EventType,
    Gender,
    InitiatedBy,
    ItemType,
    LocationType,
    RelationshipType,
)
from wulin_mud.ontology import (
    NPC,
    ActionRecord,
    Fact,
    Goal,
    HeardRumor,
    Item,
    Location,
    Memory,
    Mood,
    Personality,
    PlayerRelationship,
    Relationship,
    Rumor,
    RumorSpread,
    Secret,
    SpeechStyle,
)
from wulin_mud.world.persistence import init_db


@pytest.fixture
def engine() -> Engine:
    """Fresh in-memory SQLite engine with full schema + triggers."""
    return init_db(db_url="sqlite:///:memory:")


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as s:
        yield s


@pytest.fixture
def personality() -> Personality:
    return Personality(
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
    )


@pytest.fixture
def npc_sun(personality: Personality) -> NPC:
    return NPC(
        id="npc_sun_popo",
        name="孙婆婆",
        age=52,
        gender=Gender.FEMALE,
        role="回春堂老板娘",
        appearance="瘦小，发髻一丝不乱",
        current_location_id="loc_huichun_pharmacy",
        personality=personality,
        background="本姓孙，娘家是邻县郎中世家。",
        secrets=[
            Secret(
                id="secret_husband_death",
                content="丈夫死时身上有刀伤",
                discovery_difficulty=0.85,
                consequence_if_revealed="关系跃升",
            )
        ],
        constraints=["绝不在外人面前提起丈夫的死"],
        speech_style=SpeechStyle(
            self_reference="我",
            address_young="小哥",
            catchphrases=("药是死的，人是活的。",),
            tone="话短",
            avoids=("文绉绉的词",),
        ),
        mood=Mood(valence=-0.1, arousal=0.3),
        health=0.95,
        wealth=1200,
        energy=0.8,
        relationships={
            "npc_xiao_man": Relationship(
                other_id="npc_xiao_man",
                affection=0.95,
                trust=1.0,
                familiarity=1.0,
                relationship_type=RelationshipType.KIN,
                relationship_label="独子",
            )
        },
        player_relationship=PlayerRelationship(
            other_id="player",
            affection=-0.15,
            trust=0.3,
            familiarity=0.4,
            relationship_type=RelationshipType.STRANGER,
            relationship_label="外来年轻侠客",
            first_met_at=1.0,
            impression_summary="第一次来就为几文钱磨了半天。",
        ),
        knowledge=[Fact(id="f_qinghe_geography", content="清河镇地理熟")],
        heard_rumors=[HeardRumor(content="官道不太平", source="npc_wang_laojiu", credibility=0.7)],
        short_term_goals=[Goal(content="今天卖出 200 文药")],
        long_term_goals=[Goal(content="查明丈夫死因", priority=0.9)],
    )


@pytest.fixture
def memory_first_meeting() -> Memory:
    return Memory(
        id="mem_001",
        timestamp=1000.0,
        event_type=EventType.MET,
        participants=["player", "npc_sun_popo"],
        location_id="loc_huichun_pharmacy",
        raw_facts={"item": "止血膏", "asked_discount": 0.5},
        npc_id="npc_sun_popo",
        interpretation="这小子第一次来就砍价砍狠了。",
        emotional_charge=-0.3,
        importance=0.45,
        decay_rate=0.05,
        tags=["金钱", "砍价", "首次见面"],
    )


@pytest.fixture
def location_pharmacy() -> Location:
    return Location(
        id="loc_huichun_pharmacy",
        name="回春堂",
        type=LocationType.PHARMACY,
        description="主街中段偏南的药铺",
        current_npcs=["npc_sun_popo"],
        atmosphere="午后清淡",
        owner_npc_id="npc_sun_popo",
        connected_to=["loc_main_street"],
    )


@pytest.fixture
def item_zhixue_gao() -> Item:
    return Item(
        id="item_zhixue_gao",
        name="止血膏",
        type=ItemType.MEDICINE,
        description="疗外伤的膏药",
        base_price=80,
        location_id="loc_huichun_pharmacy",
        is_unique=False,
        metadata={"shelf_life_days": 90},
    )


@pytest.fixture
def rumor_jianghu() -> Rumor:
    return Rumor(
        id="rumor_official_road",
        created_at=2000.0,
        source_event_id=None,
        original_content="官道上最近不太平，有镖出了事",
        spread_chain=[
            RumorSpread(
                from_npc_id="npc_wang_laojiu",
                to_npc_id="npc_sun_popo",
                at_timestamp=2100.0,
                distorted_content="听说镖局出了大事",
            )
        ],
        veracity=0.7,
        spice_level=0.5,
    )


@pytest.fixture
def action_record_buy() -> ActionRecord:
    return ActionRecord(
        id="rec_001",
        timestamp=3000.0,
        action_type="BuyItem",
        actor_id="player",
        parameters={"item_id": "item_zhixue_gao", "price": 50},
        succeeded=True,
        side_effects_applied=[{"field": "NPC.wealth", "delta": 50}],
        memories_generated=["mem_001"],
        initiated_by=InitiatedBy.PLAYER_INPUT,
        llm_reasoning=None,
    )
