"""Location Object Type. See docs/ontology.md §2.5."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.core.enums import LocationType


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Immutable identity
    id: str
    name: str
    type: LocationType
    description: str

    # Mutable state
    current_npcs: list[str] = Field(default_factory=list)
    atmosphere: str = ""

    # Associations
    owner_npc_id: str | None = None
    connected_to: list[str] = Field(default_factory=list)
