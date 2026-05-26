"""Small value objects referenced by larger Object Types.

Mood, SpeechStyle, Secret, Fact, HeardRumor, Goal, RumorSpread.

These are pure pydantic models (no DB table of their own); they are
persisted as embedded JSON inside their parent rows.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Mood(BaseModel):
    """NPC's current emotional state.

    `valence` is the pleasant/unpleasant axis (-1.0 = misery, +1.0 = joy).
    `arousal` is the calm/excited axis (0.0 = sleepy, 1.0 = highly aroused).
    """

    model_config = ConfigDict(extra="forbid")

    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    arousal: float = Field(default=0.3, ge=0.0, le=1.0)


class SpeechStyle(BaseModel):
    """How an NPC speaks. Static at world-init time per docs/architecture.md."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    self_reference: str = "我"
    address_young: str | None = None
    address_old: str | None = None
    catchphrases: tuple[str, ...] = ()
    tone: str | None = None
    avoids: tuple[str, ...] = ()


class Secret(BaseModel):
    """A piece of information the NPC will not volunteer.

    See docs/npc-spec.md §5.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    content: str
    discovery_difficulty: float = Field(ge=0.0, le=1.0)
    consequence_if_revealed: str


class Fact(BaseModel):
    """A piece of objective knowledge the NPC holds.

    Distinct from Memory: a Fact is something the NPC "just knows"
    (geography, prices, recipes); a Memory is a remembered event.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    content: str


class HeardRumor(BaseModel):
    """A rumor the NPC has heard, with provenance and trust.

    The structure matches the yaml seed format. Note `source` is a free
    string because it may be either an NPC id or a generic tag like
    "street_gossip".
    """

    model_config = ConfigDict(extra="forbid")

    content: str
    source: str
    credibility: float = Field(ge=0.0, le=1.0)


class Goal(BaseModel):
    """An NPC goal. Seed YAMLs may use bare strings; we coerce them here."""

    model_config = ConfigDict(extra="forbid")

    content: str
    priority: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"content": data}
        return data


class RumorSpread(BaseModel):
    """One hop in a rumor's spread chain. See docs/ontology.md §2.7."""

    model_config = ConfigDict(extra="forbid")

    from_npc_id: str
    to_npc_id: str
    at_timestamp: float
    distorted_content: str
