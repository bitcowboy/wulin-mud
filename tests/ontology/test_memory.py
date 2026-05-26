"""Memory round-trip + write-once interpretation invariant."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from wulin_mud.core.enums import EventType
from wulin_mud.ontology import Memory, MemoryInterpretationLocked
from wulin_mud.world.persistence import memory_to_row, row_to_memory


def test_memory_dict_round_trip(memory_first_meeting: Memory) -> None:
    rebuilt = Memory.model_validate(memory_first_meeting.model_dump())
    assert rebuilt == memory_first_meeting


def test_memory_db_round_trip(session: Session, memory_first_meeting: Memory) -> None:
    session.add(memory_to_row(memory_first_meeting))
    session.commit()
    row = session.get(type(memory_to_row(memory_first_meeting)), memory_first_meeting.id)
    assert row is not None
    rebuilt = row_to_memory(row)
    assert rebuilt == memory_first_meeting


def test_memory_interpretation_locked_on_python_layer(memory_first_meeting: Memory) -> None:
    """Red line: assigning a different interpretation after the first must raise."""
    with pytest.raises(MemoryInterpretationLocked):
        memory_first_meeting.interpretation = "改一改"


def test_memory_interpretation_allows_idempotent_set(memory_first_meeting: Memory) -> None:
    """Re-assigning the same value is a no-op, not an error."""
    same = memory_first_meeting.interpretation
    memory_first_meeting.interpretation = same  # must not raise
    assert memory_first_meeting.interpretation == same


def test_empty_memory_can_have_interpretation_filled_once() -> None:
    """Initial '' interpretation can be filled exactly once."""
    m = Memory(
        id="mem_empty",
        timestamp=0.0,
        event_type=EventType.WITNESSED,
        participants=["npc_a"],
        location_id="loc_x",
        npc_id="npc_a",
        # interpretation defaults to ""
    )
    m.interpretation = "first read"
    assert m.interpretation == "first read"
    with pytest.raises(MemoryInterpretationLocked):
        m.interpretation = "second read"


def test_memory_interpretation_immutable_at_db_layer(
    session: Session, memory_first_meeting: Memory
) -> None:
    """Red line backup: the SQLite trigger blocks raw-SQL tampering too."""
    from sqlalchemy.engine import Engine

    session.add(memory_to_row(memory_first_meeting))
    session.commit()
    engine = session.get_bind()
    assert isinstance(engine, Engine)
    with pytest.raises(IntegrityError) as exc:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE memories SET interpretation = :new WHERE id = :id"),
                {"new": "tampered", "id": memory_first_meeting.id},
            )
    assert "write-once" in str(exc.value)


def test_memory_other_fields_remain_mutable(session: Session, memory_first_meeting: Memory) -> None:
    """The lock applies only to interpretation. importance/decay must stay mutable."""
    memory_first_meeting.importance = 0.9
    memory_first_meeting.last_recalled_at = 4000.0
    assert memory_first_meeting.importance == 0.9
    assert memory_first_meeting.last_recalled_at == 4000.0
