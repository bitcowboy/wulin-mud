"""Rumor Object Type. See docs/ontology.md §2.7."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.ontology.value_objects import RumorSpread


class Rumor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    created_at: float

    source_event_id: str | None = None
    original_content: str

    spread_chain: list[RumorSpread] = Field(default_factory=list)

    veracity: float = Field(ge=0.0, le=1.0)
    spice_level: float = Field(ge=0.0, le=1.0)
