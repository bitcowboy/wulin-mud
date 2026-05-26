"""Memory Object Type.

Per docs/ontology.md §2.3 and docs/architecture.md red line #2,
`interpretation` is the most critical immutability invariant in the
project. Once an LLM has rendered an NPC's first-person reading of an
event, that reading is frozen — recalling the memory later must not
re-roll the interpretation.

This module enforces immutability at the python layer; the DB layer
enforces it again via a trigger (see wulin_mud.world.persistence).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.core.enums import EventType


class MemoryInterpretationLocked(ValueError):
    """Raised on any attempt to mutate Memory.interpretation after it is set."""


class Memory(BaseModel):
    """A single NPC's memory of an event.

    One event generates N memories (one per witness). Each witness's
    `interpretation` differs because it is generated against that NPC's
    personality at the time the event occurred.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: str
    timestamp: float

    # Objective layer (shared across all witnesses)
    event_type: EventType
    participants: list[str]
    location_id: str
    raw_facts: dict[str, Any] = Field(default_factory=dict)

    # Subjective layer (this NPC's reading)
    npc_id: str
    interpretation: str = ""
    emotional_charge: float = Field(default=0.0, ge=-1.0, le=1.0)

    # Decay control
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    decay_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    last_recalled_at: float | None = None

    # Retrieval aids
    tags: list[str] = Field(default_factory=list)
    embedding: list[float] | None = None

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "interpretation":
            current = self.__dict__.get("interpretation", "")
            if current and value != current:
                raise MemoryInterpretationLocked(
                    "Memory.interpretation is write-once. "
                    "Once an interpretation has been set it cannot be modified. "
                    "See docs/architecture.md red line #2."
                )
        super().__setattr__(name, value)
