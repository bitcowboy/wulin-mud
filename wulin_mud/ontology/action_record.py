"""ActionRecord Object Type. See docs/ontology.md §2.8.

Every Action that runs leaves one ActionRecord behind. This is the
golden audit trail used for debugging, behavior analysis, and future
fine-tuning data.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from wulin_mud.core.enums import InitiatedBy


class ActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    timestamp: float
    action_type: str
    actor_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)

    succeeded: bool
    side_effects_applied: list[dict[str, Any]] = Field(default_factory=list)
    memories_generated: list[str] = Field(default_factory=list)

    initiated_by: InitiatedBy
    llm_reasoning: str | None = None
