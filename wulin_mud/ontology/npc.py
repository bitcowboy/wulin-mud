"""NPC Object Type. See docs/ontology.md §2.1.

An NPC bundles five logical groups of fields:
- immutable identity (id, name, age, gender, role)
- immutable personality (personality, background, secrets, constraints, speech_style)
- mutable state (location, mood, health, wealth, energy)
- relationships (other NPCs + the player)
- knowledge (facts, heard rumors, goals)

Per docs/architecture.md red line #3, the immutable groups must not be
re-assigned at runtime. `Personality` and `SpeechStyle` enforce this
via pydantic `frozen=True`. The remaining immutable string fields are
documented but not statically locked — mutating them outside an
authorized `PersonalityShift` Action is a contract violation that
review/CI is expected to catch.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.core.enums import Gender
from wulin_mud.ontology.personality import Personality
from wulin_mud.ontology.relationship import PlayerRelationship, Relationship
from wulin_mud.ontology.value_objects import (
    Fact,
    Goal,
    HeardRumor,
    Mood,
    Secret,
    SpeechStyle,
)


class NPC(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Immutable identity
    id: str
    name: str
    age: int = Field(ge=0)
    gender: Gender
    role: str
    appearance: str | None = None

    # Immutable personality
    personality: Personality
    background: str
    secrets: list[Secret] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    speech_style: SpeechStyle = Field(default_factory=SpeechStyle)

    # Mutable state
    current_location_id: str
    mood: Mood = Field(default_factory=Mood)
    health: float = Field(default=1.0, ge=0.0, le=1.0)
    wealth: int = Field(default=0, ge=0)
    energy: float = Field(default=1.0, ge=0.0, le=1.0)

    # Relationships
    relationships: dict[str, Relationship] = Field(default_factory=dict)
    player_relationship: PlayerRelationship | None = None

    # Knowledge
    knowledge: list[Fact] = Field(default_factory=list)
    heard_rumors: list[HeardRumor] = Field(default_factory=list)

    # Goals
    short_term_goals: list[Goal] = Field(default_factory=list)
    long_term_goals: list[Goal] = Field(default_factory=list)
