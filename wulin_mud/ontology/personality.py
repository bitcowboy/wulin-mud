"""Personality value object.

Frozen by design: per docs/architecture.md red line #3 ("人设不可漂移"),
an NPC's personality dimensions are set at world initialisation and never
mutated at runtime. The pydantic `frozen=True` config enforces this.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Personality(BaseModel):
    """OCEAN + wuxia-specific personality dimensions.

    All values are in [0.0, 1.0]. See docs/ontology.md §2.2 and
    docs/npc-spec.md §3.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # OCEAN
    openness: float = Field(ge=0.0, le=1.0)
    conscientiousness: float = Field(ge=0.0, le=1.0)
    extraversion: float = Field(ge=0.0, le=1.0)
    agreeableness: float = Field(ge=0.0, le=1.0)
    neuroticism: float = Field(ge=0.0, le=1.0)

    # Wuxia-specific
    honesty: float = Field(ge=0.0, le=1.0)
    courage: float = Field(ge=0.0, le=1.0)
    greed: float = Field(ge=0.0, le=1.0)
    loyalty: float = Field(ge=0.0, le=1.0)
    pride: float = Field(ge=0.0, le=1.0)
