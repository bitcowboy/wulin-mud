"""Relationship and PlayerRelationship Object Types.

See docs/ontology.md §2.4. Relationships are stored as one-directional
edges; bidirectional consistency is enforced at seed time, not at query
time.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.core.enums import RelationshipType


class Relationship(BaseModel):
    """An NPC's directional view of another NPC.

    A real-world friendship will appear as two Relationship rows (A→B
    and B→A), each with potentially different affection / trust values
    because the two parties may view the relationship differently.
    """

    model_config = ConfigDict(extra="forbid")

    other_id: str
    affection: float = Field(ge=-1.0, le=1.0)
    trust: float = Field(ge=0.0, le=1.0)
    familiarity: float = Field(ge=0.0, le=1.0)

    relationship_type: RelationshipType
    relationship_label: str

    notable_memory_ids: list[str] = Field(default_factory=list)
    last_interaction_at: float | None = None


class PlayerRelationship(Relationship):
    """An NPC's view of the player.

    Adds first-meeting metadata and the periodically-compressed
    impression summary that lets the prompt layer cite "how she sees the
    player now" without dumping every memory.
    """

    first_met_at: float | None = None
    impression_summary: str = ""
