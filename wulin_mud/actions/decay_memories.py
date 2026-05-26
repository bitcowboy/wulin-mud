"""DecayMemories — system action invoked by the world tick.

Per docs/ontology.md §2.3:

- Every tick, each memory's importance shrinks by
  ``exp(-decay_rate × tick_dt_game_days)``.
- Memories recalled within the current tick window skip decay
  (the "被想起的事衰减更慢" rule).
- Memories whose new importance falls below
  :data:`IMPORTANCE_FLOOR` get tagged :data:`ARCHIVED_TAG` and
  are no longer included in default retrieval.

The action is callable only by SYSTEM. The tick orchestrator
(:mod:`wulin_mud.world.tick`) is the legitimate caller; manual
invocation works for tests/dogfooding.

The mutation logic lives on ``WorldState.decay_memories_bulk`` — this
action is the thin "validate + audit" wrapper around it.
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


class DecayMemories(ActionType):
    name = "DecayMemories"
    description = "World tick step: decay Memory importance; archive faded ones."
    callable_by: ClassVar[set[CallerType]] = {CallerType.SYSTEM}

    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        tick_dt = params.get("tick_dt_game_days")
        if not isinstance(tick_dt, int | float) or isinstance(tick_dt, bool) or tick_dt < 0:
            return ValidationResult(
                ok=False, reason="tick_dt_game_days must be a non-negative number"
            )
        return ValidationResult(ok=True)

    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        return SideEffectManifest(mutates_fields=["Memory.importance", "Memory.tags"])

    async def execute(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        stats = world.decay_memories_bulk(tick_dt_game_days=float(params["tick_dt_game_days"]))
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


register_action(DecayMemories())
