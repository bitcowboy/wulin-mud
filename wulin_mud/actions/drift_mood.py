"""DriftMood — system action invoked by the world tick.

Per docs/architecture.md §4: "NPC 心情漂移：基于性格的基线和最近事件，
每个 NPC 的 mood 向其稳态回归..."

v0.1 model lives on ``WorldState.drift_mood_bulk``:
  target_valence = 0.3 × (extraversion - neuroticism)
  target_arousal = 0.3 (constant in v0.1)
  new = old + alpha × (target - old)

This action is the thin "validate + audit" wrapper. SYSTEM-only.
"""

from __future__ import annotations

from typing import Any, ClassVar

from wulin_mud.actions.base import (
    ActionResult,
    ActionType,
    CallerType,
    SideEffectManifest,
    ValidationResult,
    register_action,
)
from wulin_mud.world.state import WorldState

_DEFAULT_ALPHA = 0.1


class DriftMood(ActionType):
    name = "DriftMood"
    description = "World tick step: every NPC's mood drifts toward its personality target."
    callable_by: ClassVar[set[CallerType]] = {CallerType.SYSTEM}

    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        alpha = params.get("alpha", _DEFAULT_ALPHA)
        if not isinstance(alpha, int | float) or isinstance(alpha, bool):
            return ValidationResult(ok=False, reason="alpha must be a number")
        if not (0.0 < float(alpha) <= 1.0):
            return ValidationResult(ok=False, reason="alpha must be in (0, 1]")
        return ValidationResult(ok=True)

    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        return SideEffectManifest(mutates_fields=["NPC.mood"])

    async def execute(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        alpha = float(params.get("alpha", _DEFAULT_ALPHA))
        stats = world.drift_mood_bulk(alpha=alpha)
        record = world.build_action_record(
            action_type=self.name,
            actor_id=actor_id,
            parameters=params,
            succeeded=True,
            side_effects_applied=[stats],
        )
        world.save_action_record(record)
        return ActionResult(
            succeeded=True,
            action_record_id=record.id,
            side_effects_applied=[stats],
        )


register_action(DriftMood())
