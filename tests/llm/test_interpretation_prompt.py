"""The interpretation prompt is a pure function — assert what goes in
shows up in the output."""

from __future__ import annotations

from wulin_mud.core.enums import EventType, Gender, RelationshipType
from wulin_mud.llm.prompts import build_interpretation_prompt
from wulin_mud.ontology import (
    NPC,
    Memory,
    Mood,
    Personality,
    PlayerRelationship,
    SpeechStyle,
)


def _make_sun() -> NPC:
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
        background="本姓孙",
        constraints=["绝不在外人面前提起丈夫的死"],
        speech_style=SpeechStyle(
            self_reference="我",
            catchphrases=("药是死的，人是活的。",),
            tone="话短",
        ),
        mood=Mood(valence=-0.2, arousal=0.4),
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


def _make_memory(npc_id: str) -> Memory:
    return Memory(
        id="mem_x",
        timestamp=2000.0,
        event_type=EventType.HAGGLED,
        participants=["player", npc_id],
        location_id="loc_huichun_pharmacy",
        raw_facts={"item": "止血膏", "asked_discount": 0.5},
        npc_id=npc_id,
        interpretation="",
        emotional_charge=0.0,
        importance=0.4,
        tags=["金钱"],
    )


def test_prompt_includes_npc_identity_and_personality() -> None:
    sun = _make_sun()
    mem = _make_memory(sun.id)
    prompt = build_interpretation_prompt(npc=sun, memory=mem, actor_id="player")

    # The persona dimensions matter to the LLM; they must be in the user text.
    assert "孙婆婆" in prompt.user
    assert "回春堂老板娘" in prompt.user
    assert "honesty=0.80" in prompt.user
    assert "pride=0.60" in prompt.user
    # Speech style anchors voice consistency.
    assert "药是死的" in prompt.user
    # Current mood goes in unchanged.
    assert "valence=-0.20" in prompt.user
    # Relationship summary helps the LLM color the read.
    assert "affection=-0.15" in prompt.user
    assert "磨过价的小子" in prompt.user
    # Raw facts must be present so the LLM knows what happened.
    assert "止血膏" in prompt.user
    # The system prompt frames the task (write-once + first-person).
    assert "固化" in prompt.system
    assert "第一人称" in prompt.system


def test_prompt_with_no_player_relationship_notes_first_meeting() -> None:
    sun = _make_sun()
    sun.player_relationship = None
    mem = _make_memory(sun.id)
    prompt = build_interpretation_prompt(npc=sun, memory=mem, actor_id="player")
    assert "第一次" in prompt.user or "不熟" in prompt.user


def test_prompt_with_unknown_actor_npc_falls_back_gracefully() -> None:
    sun = _make_sun()
    mem = _make_memory(sun.id)
    prompt = build_interpretation_prompt(npc=sun, memory=mem, actor_id="npc_some_stranger")
    # No relationship row — we still produce a usable prompt.
    assert "npc_some_stranger" in prompt.user


def test_recent_context_memories_show_up_in_prompt() -> None:
    """Prior interpretations are surfaced so the LLM stays grounded
    across events about the same actor."""
    sun = _make_sun()
    mem = _make_memory(sun.id)
    prior = Memory(
        id="prior_x",
        timestamp=1000.0,
        event_type=EventType.OFFENDED,
        participants=["player", sun.id],
        location_id=mem.location_id,
        npc_id=sun.id,
        interpretation="这小子刚才嘴上没分寸，让我心里堵了一下。",
        importance=0.6,
        emotional_charge=-0.4,
    )
    prompt = build_interpretation_prompt(
        npc=sun, memory=mem, actor_id="player", recent_context=[prior]
    )
    assert "嘴上没分寸" in prompt.user
    # The instruction-line about coloring by recent state should also be there.
    assert "冒犯" in prompt.user


def test_recent_context_absent_renders_a_polite_blank() -> None:
    """No prior context → render an empty marker so the LLM doesn't
    hallucinate history."""
    sun = _make_sun()
    mem = _make_memory(sun.id)
    prompt = build_interpretation_prompt(npc=sun, memory=mem, actor_id="player")
    assert "没有什么关于他的印象" in prompt.user


def test_recent_context_skips_memories_with_empty_interpretation() -> None:
    """Legacy / in-flight rows with empty interpretation are filtered out."""
    sun = _make_sun()
    mem = _make_memory(sun.id)
    empty_one = Memory(
        id="m_empty",
        timestamp=999.0,
        event_type=EventType.TALKED,
        participants=["player", sun.id],
        location_id=mem.location_id,
        npc_id=sun.id,
        # interpretation defaults to ""
        importance=0.3,
    )
    prompt = build_interpretation_prompt(
        npc=sun, memory=mem, actor_id="player", recent_context=[empty_one]
    )
    # No interpretation to show → fallback "没有什么..." line
    assert "没有什么关于他的印象" in prompt.user
