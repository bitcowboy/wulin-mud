"""MoveTo — change the actor's current location.

See docs/action-types.md §3.6. Movement deliberately does NOT generate
a per-witness Memory in v0.1; people watching someone walk by would
flood the memory store with low-signal rows. The mutation is still
audited via the ActionRecord.
"""

from __future__ import annotations

from typing import Any, ClassVar

from wulin_mud.actions._helpers import actor_location_id, ensure_player
from wulin_mud.actions.base import (
    ActionResult,
    ActionType,
    CallerType,
    SideEffectManifest,
    ValidationResult,
    WitnessesRule,
    register_action,
)
from wulin_mud.ontology import PLAYER_ID
from wulin_mud.world.state import WorldState


class MoveTo(ActionType):
    name = "MoveTo"
    description = "走到相邻的位置。"
    callable_by: ClassVar[set[CallerType]] = {CallerType.PLAYER, CallerType.NPC}

    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        destination_id = params.get("destination_id")
        if not isinstance(destination_id, str) or not destination_id:
            return ValidationResult(ok=False, reason="missing destination_id")

        destination = world.get_location(destination_id)
        if destination is None:
            return ValidationResult(
                ok=False, reason=f"destination {destination_id!r} does not exist"
            )

        try:
            current_loc_id = actor_location_id(world, actor_id)
        except LookupError as exc:
            return ValidationResult(ok=False, reason=str(exc))

        if current_loc_id == destination_id:
            return ValidationResult(ok=False, reason="already at destination")

        current = world.get_location(current_loc_id)
        if current is None:
            return ValidationResult(
                ok=False, reason=f"current location {current_loc_id!r} does not exist"
            )
        if destination_id not in current.connected_to:
            return ValidationResult(
                ok=False,
                reason=f"destination {destination_id!r} is not connected to {current_loc_id!r}",
            )

        return ValidationResult(ok=True)

    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        return SideEffectManifest(
            mutates_fields=[
                "NPC.current_location_id",
                "PlayerState.current_location_id",
                "Location.current_npcs",
            ],
            witnesses_rule=WitnessesRule.SAME_LOCATION,
        )

    async def execute(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        destination_id: str = params["destination_id"]
        from_id = actor_location_id(world, actor_id)
        side_effects: list[dict[str, Any]] = []

        # 1) Update Location.current_npcs on both ends (NPC movers only —
        #    the player isn't tracked in Location.current_npcs because
        #    Location.current_npcs is typed list[npc_id]).
        if actor_id != PLAYER_ID:
            from_loc = world.get_location(from_id)
            assert from_loc is not None
            if actor_id in from_loc.current_npcs:
                new_current = [n for n in from_loc.current_npcs if n != actor_id]
                world.save_location(from_loc.model_copy(update={"current_npcs": new_current}))

            to_loc = world.get_location(destination_id)
            assert to_loc is not None
            if actor_id not in to_loc.current_npcs:
                new_current = [*to_loc.current_npcs, actor_id]
                world.save_location(to_loc.model_copy(update={"current_npcs": new_current}))

        # 2) Update the actor's own location pointer.
        if actor_id == PLAYER_ID:
            player = ensure_player(world)
            world.save_player(player.model_copy(update={"current_location_id": destination_id}))
            side_effects.append(
                {
                    "field": "PlayerState.current_location_id",
                    "from": from_id,
                    "to": destination_id,
                }
            )
        else:
            npc = world.get_npc(actor_id)
            assert npc is not None  # guaranteed by validate()
            world.save_npc(npc.model_copy(update={"current_location_id": destination_id}))
            side_effects.append(
                {
                    "field": "NPC.current_location_id",
                    "npc_id": actor_id,
                    "from": from_id,
                    "to": destination_id,
                }
            )

        record = world.build_action_record(
            action_type=self.name,
            actor_id=actor_id,
            parameters=params,
            succeeded=True,
            side_effects_applied=side_effects,
        )
        world.save_action_record(record)

        return ActionResult(
            succeeded=True,
            action_record_id=record.id,
            side_effects_applied=side_effects,
        )


register_action(MoveTo())
