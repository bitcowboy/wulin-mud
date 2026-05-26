"""run_tick orchestrator: drives both system actions in one tick."""

from __future__ import annotations

import pytest
from sqlmodel import Session

from wulin_mud.core.enums import EventType, Gender
from wulin_mud.ontology import (
    NPC,
    Memory,
    Mood,
    Personality,
)
from wulin_mud.world.persistence import MemoryRow, NpcRow, init_db
from wulin_mud.world.tick import run_tick


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
def session() -> Session:
    engine = init_db(db_url="sqlite:///:memory:")
    with Session(engine) as s:
        yield s


@pytest.fixture
def seeded(session: Session) -> Session:
    from wulin_mud.world.state import WorldState

    w = WorldState(session, now=1000.0)
    sun = NPC(
        id="npc_sun_popo",
        name="孙婆婆",
        age=52,
        gender=Gender.FEMALE,
        role="回春堂老板娘",
        current_location_id="loc_huichun_pharmacy",
        personality=_personality(),
        background="x",
        mood=Mood(valence=0.5, arousal=0.5),  # off-target on purpose
    )
    mem = Memory(
        id="mem_1",
        timestamp=900.0,
        event_type=EventType.MET,
        participants=["player", "npc_sun_popo"],
        location_id="loc_huichun_pharmacy",
        npc_id="npc_sun_popo",
        importance=1.0,
        decay_rate=0.5,
    )
    w.save_npc(sun)
    w.save_memory(mem)
    session.commit()
    return session


async def test_run_tick_drifts_mood_and_decays_memories(seeded: Session) -> None:
    result = await run_tick(session=seeded, tick_dt_game_days=1.0)
    assert result.drift_mood.succeeded
    assert result.decay_memories.succeeded

    seeded.expire_all()
    sun_row = seeded.get(NpcRow, "npc_sun_popo")
    assert sun_row is not None
    # Mood moved closer to (0, 0.3) target — strictly between start and target.
    assert sun_row.mood["valence"] < 0.5
    assert sun_row.mood["arousal"] < 0.5

    mem_row = seeded.get(MemoryRow, "mem_1")
    assert mem_row is not None
    # importance shrunk (exp(-0.5) ≈ 0.6065)
    assert mem_row.importance == pytest.approx(0.6065, abs=1e-3)


async def test_repeated_ticks_converge_toward_target(seeded: Session) -> None:
    """After many ticks mood should be very close to the personality target."""
    for _ in range(100):
        await run_tick(session=seeded, tick_dt_game_days=1.0)
    seeded.expire_all()
    sun_row = seeded.get(NpcRow, "npc_sun_popo")
    assert sun_row is not None
    # neutral personality → target valence 0
    assert abs(sun_row.mood["valence"]) < 0.01
    # target arousal 0.3
    assert abs(sun_row.mood["arousal"] - 0.3) < 0.01


async def test_run_tick_writes_audit_records(seeded: Session) -> None:
    """Both system actions leave ActionRecords with initiated_by=WORLD_TICK."""
    from wulin_mud.world.persistence import ActionRecordRow

    result = await run_tick(session=seeded, tick_dt_game_days=1.0)
    drift_row = seeded.get(ActionRecordRow, result.drift_mood.action_record_id)
    decay_row = seeded.get(ActionRecordRow, result.decay_memories.action_record_id)
    assert drift_row is not None and drift_row.action_type == "DriftMood"
    assert decay_row is not None and decay_row.action_type == "DecayMemories"
    assert drift_row.initiated_by == "world_tick"
    assert decay_row.initiated_by == "world_tick"
    assert drift_row.actor_id == "system_tick"
