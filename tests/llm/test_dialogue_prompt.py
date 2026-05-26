"""The dialogue prompt threads identity, constraints, memories, and the
player's input into a single (system, user) pair."""

from __future__ import annotations

from wulin_mud.core.enums import EventType, Gender, RelationshipType
from wulin_mud.llm.prompts import build_dialogue_prompt
from wulin_mud.ontology import (
    NPC,
    Fact,
    HeardRumor,
    Memory,
    Mood,
    Personality,
    PlayerRelationship,
    Secret,
    SpeechStyle,
)


def _sun() -> NPC:
    return NPC(
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
        background="本姓孙，娘家是郎中世家",
        secrets=[
            Secret(
                id="s1",
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
        knowledge=[Fact(id="f1", content="清河镇所有街巷")],
        heard_rumors=[HeardRumor(content="官道不太平", source="npc_wang_laojiu", credibility=0.7)],
        player_relationship=PlayerRelationship(
            other_id="player",
            affection=-0.15,
            trust=0.3,
            familiarity=0.4,
            relationship_type=RelationshipType.STRANGER,
            relationship_label="外来年轻侠客",
            first_met_at=1.0,
            impression_summary="磨过价的小子",
        ),
    )


def _memory(*, interp: str, event_type: EventType = EventType.MET) -> Memory:
    return Memory(
        id="m_x",
        timestamp=2000.0,
        event_type=event_type,
        participants=["player", "npc_sun_popo"],
        location_id="loc_huichun_pharmacy",
        npc_id="npc_sun_popo",
        interpretation=interp,
        importance=0.5,
    )


def test_system_prompt_carries_the_anti_drift_rules() -> None:
    p = build_dialogue_prompt(npc=_sun(), actor_id="player", player_input="婆婆好。")
    # The "铁律" section + key phrases from docs/llm-integration.md §2.
    assert "铁律" in p.system
    assert "constraints" in p.system
    assert "speech_style" in p.system
    assert "你不知道自己是 NPC" in p.system


def test_user_prompt_includes_identity_and_constraints() -> None:
    p = build_dialogue_prompt(npc=_sun(), actor_id="player", player_input="婆婆好。")
    assert "孙婆婆" in p.user
    assert "52" in p.user
    assert "回春堂老板娘" in p.user
    assert "绝不在外人面前提起丈夫的死" in p.user
    assert "药是死的" in p.user


def test_user_prompt_includes_secrets_for_self_awareness() -> None:
    """The NPC can know her own secrets — she just won't volunteer them."""
    p = build_dialogue_prompt(npc=_sun(), actor_id="player", player_input="你丈夫呢？")
    assert "丈夫死时身上有刀伤" in p.user


def test_user_prompt_includes_knowledge_and_rumors() -> None:
    p = build_dialogue_prompt(npc=_sun(), actor_id="player", player_input="哪里能找到血草？")
    assert "清河镇所有街巷" in p.user
    assert "官道不太平" in p.user


def test_user_prompt_renders_memory_interpretations_not_raw_facts() -> None:
    """Memories show the NPC's *interpretation* — not the JSON raw_facts.
    That keeps the persona's voice consistent across turns."""
    mem = _memory(interp="这小子第一次来就磨价，没规矩。")
    p = build_dialogue_prompt(
        npc=_sun(),
        actor_id="player",
        player_input="婆婆好。",
        relevant_memories=[mem],
    )
    assert "这小子第一次来就磨价，没规矩。" in p.user
    # raw_facts dict should NOT be inlined when interpretation exists.
    assert "raw_facts" not in p.user


def test_user_prompt_falls_back_when_interpretation_is_empty() -> None:
    """Legacy memories (pre-LLM-layer) may have empty interpretation; we
    show event type + raw_facts to avoid silently dropping context."""
    mem = _memory(interp="")
    p = build_dialogue_prompt(
        npc=_sun(),
        actor_id="player",
        player_input="婆婆好。",
        relevant_memories=[mem],
    )
    assert "无主观印象" in p.user


def test_user_prompt_renders_recent_dialogue_in_order() -> None:
    turns = [
        Memory(
            id=f"t{i}",
            timestamp=1000.0 + i,
            event_type=EventType.TALKED,
            participants=["player", "npc_sun_popo"],
            location_id="loc_huichun_pharmacy",
            npc_id="npc_sun_popo",
            raw_facts={"said": f"对方话 {i}", "replied": f"婆婆话 {i}"},
        )
        for i in range(2)
    ]
    p = build_dialogue_prompt(
        npc=_sun(),
        actor_id="player",
        player_input="再说一次。",
        recent_dialogue=turns,
    )
    # Both turns must appear in order.
    pos_0_you = p.user.find("婆婆话 0")
    pos_1_you = p.user.find("婆婆话 1")
    assert 0 < pos_0_you < pos_1_you


def test_user_prompt_carries_the_player_input_verbatim() -> None:
    p = build_dialogue_prompt(
        npc=_sun(),
        actor_id="player",
        player_input="婆婆，今儿气色不错。前几天你说的那个跌打的方子，能再帮我抓一副么？",
    )
    assert "婆婆，今儿气色不错" in p.user
    assert "跌打的方子" in p.user
