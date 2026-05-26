"""Pydantic schema for eval scenario YAMLs.

The on-disk format matches the existing
``tests/eval/npc_consistency/sun_popo/scenario_01_first_buy.yaml`` —
that file was the scaffold; this module defines its strict schema so
every new scenario validates.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class HardAssertionType(StrEnum):
    """Pure-Python checks on the NPC's reply."""

    MAX_SENTENCES = "max_sentences"
    """The reply must contain ≤ ``value`` sentences (terminated by 。！？).
    Use to enforce 话短."""

    MUST_NOT_CONTAIN = "must_not_contain"
    """None of the strings in ``values`` may appear anywhere in the reply.
    Use to enforce constraints (forbidden topics, banned words)."""

    MUST_CONTAIN_ONE_OF = "must_contain_one_of"
    """At least one of ``values`` must appear in the reply. Use to enforce
    speech-style anchors (self-reference, catchphrases)."""


class SoftAssertionType(StrEnum):
    """LLM-as-judge checks, scored 1-5."""

    IN_CHARACTER = "in_character"
    """Does the reply read as the NPC's personality + constraints would
    have it read?"""

    SPEECH_STYLE_MATCH = "speech_style_match"
    """Does the wording match the NPC's documented speech_style?"""


class HardAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: HardAssertionType
    value: int | None = None
    """Used by MAX_SENTENCES."""
    values: list[str] = Field(default_factory=list)
    """Used by MUST_NOT_CONTAIN and MUST_CONTAIN_ONE_OF."""
    reason: str = ""


class SoftAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: SoftAssertionType
    criterion: str
    """The rubric the judge LLM scores against."""
    threshold: float = 3.5
    """Reply must score ≥ this (out of 5) for the assertion to pass."""


class AssertionGroups(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hard: list[HardAssertion] = Field(default_factory=list)
    soft: list[SoftAssertion] = Field(default_factory=list)


class NpcStateOverride(BaseModel):
    """Optional fields to overlay on the seeded NPC before running."""

    model_config = ConfigDict(extra="forbid")
    mood: dict[str, float] | None = None
    energy: float | None = None
    current_location_id: str | None = None


class PlayerRelationshipOverride(BaseModel):
    """Optional fields for the NPC's PlayerRelationship."""

    model_config = ConfigDict(extra="forbid")
    first_met_at: float | None = None
    affection: float | None = None
    trust: float | None = None
    familiarity: float | None = None
    impression_summary: str | None = None
    # Memories the NPC already holds about the player (rendered into the
    # prompt). For scenarios that exercise "she remembers the offense".
    memories: list[dict[str, Any]] = Field(default_factory=list)


class InitialState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    npc: NpcStateOverride = Field(default_factory=NpcStateOverride)
    player_relationship: PlayerRelationshipOverride = Field(
        default_factory=PlayerRelationshipOverride
    )


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    npc_id: str

    initial_state: InitialState = Field(default_factory=InitialState)
    player_input: str
    """The line the player says. Routed through the Talk action against
    ``npc_id``."""

    assertions: AssertionGroups

    expected_behavior_notes: str = ""
    """Free-form designer notes about what 'passing' looks like.
    Not parsed — read it when you're writing or revising a scenario."""


def load_scenario(path: str | Path) -> Scenario:
    """Read + validate a scenario YAML file."""
    p = Path(path)
    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Scenario.model_validate(raw)
