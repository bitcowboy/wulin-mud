"""Greet — bump familiarity and leave a low-importance Memory.

See docs/action-types.md §3.1. The simplest social Action; useful as
the "does the framework work end-to-end?" smoke test.
"""

from __future__ import annotations

from typing import Any

from wulin_mud.actions._helpers import (
    actor_location_id,
    clamp,
    ensure_player_relationship,
    ensure_relationship,
)
from wulin_mud.actions.base import (
    ActionResult,
    ActionType,
    CallerType,
    SideEffectManifest,
    ValidationResult,
    WitnessesRule,
    register_action,
)
from wulin_mud.core.enums import EventType
from wulin_mud.ontology import PLAYER_ID
from wulin_mud.world.state import WorldState


_FAMILIARITY_INCREMENT = 0.05


class Greet(ActionType):
    name = "Greet"
    description = "打个招呼。建立或加深 familiarity。"
    callable_by = {CallerType.PLAYER, CallerType.NPC}

    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        target_id = params.get("target_id")
        if not isinstance(target_id, str) or not target_id:
            return ValidationResult(ok=False, reason="missing target_id")
        if target_id == actor_id:
            return ValidationResult(ok=False, reason="cannot greet yourself")

        target = world.get_npc(target_id)
        if target is None:
            return ValidationResult(ok=False, reason=f"target {target_id!r} does not exist")

        try:
            actor_loc = actor_location_id(world, actor_id)
        except LookupError as exc:
            return ValidationResult(ok=False, reason=str(exc))

        if target.current_location_id != actor_loc:
            return ValidationResult(
                ok=False,
                reason=f"target is at {target.current_location_id}, actor is at {actor_loc}",
            )
        return ValidationResult(ok=True)

    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        return SideEffectManifest(
            mutates_fields=[
                "NPC.relationships.familiarity",
                "NPC.player_relationship.familiarity",
            ],
            witnesses_rule=WitnessesRule.SAME_LOCATION,
        )

    async def execute(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        target_id: str = params["target_id"]
        target = world.get_npc(target_id)
        assert target is not None  # guaranteed by validate()
        location_id = target.current_location_id

        side_effects: list[dict[str, Any]] = []

        # 1) Bump familiarity on the target's side.
        if actor_id == PLAYER_ID:
            pr = ensure_player_relationship(target, first_met_at=world.now)
            old = pr.familiarity
            target.player_relationship = pr.model_copy(
                update={"familiarity": clamp(old + _FAMILIARITY_INCREMENT, low=0.0, high=1.0)}
            )
            side_effects.append(
                {
                    "field": "NPC.player_relationship.familiarity",
                    "npc_id": target_id,
                    "from": old,
                    "to": target.player_relationship.familiarity,
                }
            )
        else:
            rel = ensure_relationship(target, actor_id)
            old = rel.familiarity
            target.relationships[actor_id] = rel.model_copy(
                update={"familiarity": clamp(old + _FAMILIARITY_INCREMENT, low=0.0, high=1.0)}
            )
            side_effects.append(
                {
                    "field": "NPC.relationships.familiarity",
                    "npc_id": target_id,
                    "other_id": actor_id,
                    "from": old,
                    "to": target.relationships[actor_id].familiarity,
                }
            )
        world.save_npc(target)

        # 2) Generate witness memories.
        witnesses = world.witnesses_for(
            WitnessesRule.SAME_LOCATION, location_id=location_id
        )
        memory_ids = world.record_witnessed_event(
            witnesses=witnesses,
            event_type=EventType.MET,
            participants=[actor_id, target_id],
            location_id=location_id,
            raw_facts={"greeted": target_id, "by": actor_id},
            base_importance=0.15,
            base_emotional_charge=0.0,
            tags=["招呼"],
        )

        # 3) Audit record.
        record = world.build_action_record(
            action_type=self.name,
            actor_id=actor_id,
            parameters=params,
            succeeded=True,
            side_effects_applied=side_effects,
            memories_generated=memory_ids,
        )
        world.save_action_record(record)

        return ActionResult(
            succeeded=True,
            action_record_id=record.id,
            side_effects_applied=side_effects,
            memories_generated=memory_ids,
        )


register_action(Greet())
