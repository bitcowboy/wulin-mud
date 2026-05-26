"""generate_interpretation() — provider call + assertion that the prompt
actually carries the witness's data."""

from __future__ import annotations

from wulin_mud.core.enums import EventType, Gender
from wulin_mud.llm import FakeProvider, generate_interpretation
from wulin_mud.ontology import NPC, Memory, Personality


def _personality() -> Personality:
    return Personality(
        openness=0.5,
        conscientiousness=0.5,
        extraversion=0.5,
        agreeableness=0.5,
        neuroticism=0.5,
        honesty=0.5,
        courage=0.5,
        greed=0.5,
        loyalty=0.5,
        pride=0.5,
    )


def _npc() -> NPC:
    return NPC(
        id="npc_sun_popo",
        name="孙婆婆",
        age=52,
        gender=Gender.FEMALE,
        role="回春堂老板娘",
        current_location_id="loc_huichun_pharmacy",
        personality=_personality(),
        background="本姓孙",
    )


def _memory() -> Memory:
    return Memory(
        id="mem_x",
        timestamp=2000.0,
        event_type=EventType.MET,
        participants=["player", "npc_sun_popo"],
        location_id="loc_huichun_pharmacy",
        raw_facts={"by": "player"},
        npc_id="npc_sun_popo",
    )


async def test_generate_interpretation_returns_provider_output() -> None:
    fp = FakeProvider(default="这小子，看着年轻。")
    out = await generate_interpretation(
        provider=fp, npc=_npc(), memory=_memory(), actor_id="player"
    )
    assert out == "这小子，看着年轻。"
    assert len(fp.calls) == 1


async def test_generate_interpretation_strips_whitespace() -> None:
    fp = FakeProvider(default="  这小子，看着年轻。\n")
    out = await generate_interpretation(
        provider=fp, npc=_npc(), memory=_memory(), actor_id="player"
    )
    assert out == "这小子，看着年轻。"


async def test_generate_interpretation_passes_npc_data_through_prompt() -> None:
    """The provider must see the witness's actual identity in the user prompt."""
    fp = FakeProvider(default="ok")
    await generate_interpretation(provider=fp, npc=_npc(), memory=_memory(), actor_id="player")
    user = fp.calls[0].user
    assert "孙婆婆" in user
    assert "回春堂老板娘" in user


async def test_generate_interpretation_uses_lower_temperature_by_default() -> None:
    """Interpretations want characteristic, not creative output."""
    fp = FakeProvider(default="ok")
    await generate_interpretation(provider=fp, npc=_npc(), memory=_memory(), actor_id="player")
    assert fp.calls[0].temperature <= 0.5
