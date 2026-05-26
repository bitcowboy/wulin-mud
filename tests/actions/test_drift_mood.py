"""DriftMood: NPC mood gravitates toward a personality-derived target."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from tests.actions.conftest import FIXED_NOW
from wulin_mud.actions import execute_action
from wulin_mud.core.enums import InitiatedBy
from wulin_mud.world.state import WorldState


async def test_drift_pulls_valence_toward_personality_target(
    session: Session, world_seeded: WorldState
) -> None:
    """Granny Sun: extraversion=0.85? No — she's been built with the
    minimal personality (all 0.5 except conscientiousness/pride).
    Use the conftest sun and check the math directly."""
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    sun = sun.model_copy(update={"mood": sun.mood.model_copy(update={"valence": 0.5})})
    world_seeded.save_npc(sun)
    session.commit()

    # target_valence = 0.3 * (extraversion - neuroticism) = 0.3 * (0.5 - 0.5) = 0
    # new = 0.5 + 0.1 * (0 - 0.5) = 0.45
    result = await execute_action(
        session=session,
        action_name="DriftMood",
        params={"alpha": 0.1},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded
    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None
    assert sun_after.mood.valence == pytest.approx(0.45, abs=1e-6)


async def test_drift_moves_arousal_toward_default(
    session: Session, world_seeded: WorldState
) -> None:
    sun = world_seeded.get_npc("npc_sun_popo")
    assert sun is not None
    sun = sun.model_copy(update={"mood": sun.mood.model_copy(update={"arousal": 0.9})})
    world_seeded.save_npc(sun)
    session.commit()

    result = await execute_action(
        session=session,
        action_name="DriftMood",
        params={"alpha": 0.1},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded
    session.expire_all()
    sun_after = world_seeded.get_npc("npc_sun_popo")
    assert sun_after is not None
    # target arousal = 0.3; new = 0.9 + 0.1 * (0.3 - 0.9) = 0.84
    assert sun_after.mood.arousal == pytest.approx(0.84, abs=1e-6)


async def test_drift_with_extreme_personality_pulls_negative(
    session: Session, world_seeded: WorldState
) -> None:
    """An NPC with high neuroticism should drift toward negative valence."""
    from wulin_mud.core.enums import Gender
    from wulin_mud.ontology import NPC, Mood, Personality

    gloomy = NPC(
        id="npc_gloomy",
        name="郁先生",
        age=40,
        gender=Gender.MALE,
        role="测试用",
        current_location_id="loc_huichun_pharmacy",
        personality=Personality(
            openness=0.5,
            conscientiousness=0.5,
            extraversion=0.1,
            agreeableness=0.5,
            neuroticism=0.9,
            honesty=0.5,
            courage=0.5,
            greed=0.5,
            loyalty=0.5,
            pride=0.5,
        ),
        background="测试",
        mood=Mood(valence=0.0, arousal=0.3),
    )
    world_seeded.save_npc(gloomy)
    session.commit()

    result = await execute_action(
        session=session,
        action_name="DriftMood",
        params={"alpha": 0.1},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded
    session.expire_all()
    g = world_seeded.get_npc("npc_gloomy")
    assert g is not None
    # target = 0.3 * (0.1 - 0.9) = -0.24
    # new = 0 + 0.1 * (-0.24 - 0) = -0.024
    assert g.mood.valence < 0


async def test_drift_action_record_is_audited(session: Session, world_seeded: WorldState) -> None:
    result = await execute_action(
        session=session,
        action_name="DriftMood",
        params={"alpha": 0.1},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded
    assert result.side_effects_applied
    # stats dict reports moved count >= 1 (Granny Sun is in the world)
    moved = result.side_effects_applied[0].get("moved", 0)
    assert moved >= 1


async def test_drift_rejects_invalid_alpha(session: Session, world_seeded: WorldState) -> None:
    result = await execute_action(
        session=session,
        action_name="DriftMood",
        params={"alpha": 0},
        actor_id="system_tick",
        initiated_by=InitiatedBy.WORLD_TICK,
        now=FIXED_NOW,
    )
    assert result.succeeded is False
    assert result.narrative_hint and "alpha" in result.narrative_hint


async def test_drift_not_callable_by_player(session: Session, world_seeded: WorldState) -> None:
    """System action; player must not be able to invoke it."""
    from wulin_mud.actions import ActionCallerNotPermitted

    with pytest.raises(ActionCallerNotPermitted):
        await execute_action(
            session=session,
            action_name="DriftMood",
            params={"alpha": 0.1},
            actor_id="player",
            initiated_by=InitiatedBy.PLAYER_INPUT,
            now=FIXED_NOW,
        )
