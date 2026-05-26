"""generate_dialogue() — uses higher temperature, returns provider output."""

from __future__ import annotations

from wulin_mud.core.enums import Gender
from wulin_mud.llm import FakeProvider, generate_dialogue
from wulin_mud.ontology import NPC, Personality


def _npc() -> NPC:
    return NPC(
        id="npc_sun_popo",
        name="孙婆婆",
        age=52,
        gender=Gender.FEMALE,
        role="回春堂老板娘",
        current_location_id="loc_huichun_pharmacy",
        personality=Personality(
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
        ),
        background="本姓孙",
    )


async def test_generate_dialogue_returns_provider_output_stripped() -> None:
    fp = FakeProvider(default="  小哥，进来坐。\n")
    out = await generate_dialogue(
        provider=fp, npc=_npc(), actor_id="player", player_input="婆婆好。"
    )
    assert out == "小哥，进来坐。"


async def test_generate_dialogue_uses_warmer_temperature_than_interpretation() -> None:
    """Dialogue benefits from phrasing variety; interpretation does not."""
    fp = FakeProvider(default="ok")
    await generate_dialogue(provider=fp, npc=_npc(), actor_id="player", player_input="嗯。")
    assert fp.calls[0].temperature >= 0.6


async def test_generate_dialogue_includes_player_input_in_user_prompt() -> None:
    fp = FakeProvider(default="ok")
    await generate_dialogue(
        provider=fp, npc=_npc(), actor_id="player", player_input="婆婆，止血膏多少文？"
    )
    assert "止血膏多少文" in fp.calls[0].user
