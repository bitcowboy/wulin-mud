"""Personality is frozen at construction; runtime mutation must fail."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from wulin_mud.ontology import Personality


def test_personality_round_trip_dict(personality: Personality) -> None:
    data = personality.model_dump()
    rebuilt = Personality.model_validate(data)
    assert rebuilt == personality


def test_personality_is_frozen_runtime_mutation_rejected(personality: Personality) -> None:
    """Red line: personality dimensions are immutable after construction."""
    with pytest.raises(ValidationError):
        personality.openness = 0.99


def test_personality_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        Personality(
            openness=1.5,  # out of range
            conscientiousness=0.5,
            extraversion=0.5,
            agreeableness=0.5,
            neuroticism=0.5,
            honesty=0.5,
            courage=0.5,
            greed=0.5,
            loyalty=0.5,
            pride=0.5,
        )
