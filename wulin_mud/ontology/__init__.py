"""Object Type definitions per docs/ontology.md.

Domain pydantic models for: NPC, Personality, Memory, Relationship,
PlayerRelationship, Location, Item, Rumor, ActionRecord.

These models are the canonical in-memory representation of world state.
SQLModel row classes in wulin_mud.world.persistence persist them to
SQLite, but the persistence layer always converts back to these
classes — they are what the rest of the engine consumes.
"""

from wulin_mud.ontology.action_record import ActionRecord
from wulin_mud.ontology.item import Item
from wulin_mud.ontology.location import Location
from wulin_mud.ontology.memory import Memory, MemoryInterpretationLocked
from wulin_mud.ontology.npc import NPC
from wulin_mud.ontology.personality import Personality
from wulin_mud.ontology.relationship import PlayerRelationship, Relationship
from wulin_mud.ontology.rumor import Rumor
from wulin_mud.ontology.value_objects import (
    Fact,
    Goal,
    HeardRumor,
    Mood,
    RumorSpread,
    Secret,
    SpeechStyle,
)

__all__ = [
    "NPC",
    "ActionRecord",
    "Fact",
    "Goal",
    "HeardRumor",
    "Item",
    "Location",
    "Memory",
    "MemoryInterpretationLocked",
    "Mood",
    "Personality",
    "PlayerRelationship",
    "Relationship",
    "Rumor",
    "RumorSpread",
    "Secret",
    "SpeechStyle",
]
