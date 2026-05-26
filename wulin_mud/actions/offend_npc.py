"""OffendNPC — drop affection, sour mood, leave a negative Memory.

See docs/action-types.md §3.4. The amount of damage is uniform in v0.1
(personality-based scaling will land with the LLM layer once it can
weigh ``pride`` and ``agreeableness`` against the offense).
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


_AFFECTION_DROP = 0.15
_MOOD_VALENCE_DROP = 0.1


class OffendNPC(ActionType):
    name = "OffendNPC"
    description = "言语或行为冒犯。降低 affection 与 mood.valence。"
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
            return ValidationResult(ok=False, reason="cannot offend yourself")

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

        description = params.get("description")
        if description is not None and not isinstance(description, str):
            return ValidationResult(ok=False, reason="description must be a string")

        return ValidationResult(ok=True)

    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        return SideEffectManifest(
            mutates_fields=[
                "NPC.relationships.affection",
                "NPC.player_relationship.affection",
                "NPC.mood.valence",
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
        description: str | None = params.get("description")
        target = world.get_npc(target_id)
        assert target is not None
        location_id = target.current_location_id

        side_effects: list[dict[str, Any]] = []

        # 1) Affection on the target's side toward actor.
        if actor_id == PLAYER_ID:
            pr = ensure_player_relationship(target, first_met_at=world.now)
            new_aff = clamp(pr.affection - _AFFECTION_DROP, low=-1.0, high=1.0)
            target.player_relationship = pr.model_copy(update={"affection": new_aff})
            side_effects.append(
                {
                    "field": "NPC.player_relationship.affection",
                    "npc_id": target_id,
                    "from": pr.affection,
                    "to": new_aff,
                }
            )
        else:
            rel = ensure_relationship(target, actor_id)
            new_aff = clamp(rel.affection - _AFFECTION_DROP, low=-1.0, high=1.0)
            target.relationships[actor_id] = rel.model_copy(update={"affection": new_aff})
            side_effects.append(
                {
                    "field": "NPC.relationships.affection",
                    "npc_id": target_id,
                    "other_id": actor_id,
                    "from": rel.affection,
                    "to": new_aff,
                }
            )

        # 2) Mood valence drop.
        old_valence = target.mood.valence
        new_valence = clamp(old_valence - _MOOD_VALENCE_DROP, low=-1.0, high=1.0)
        target.mood = target.mood.model_copy(update={"valence": new_valence})
        side_effects.append(
            {
                "field": "NPC.mood.valence",
                "npc_id": target_id,
                "from": old_valence,
                "to": new_valence,
            }
        )

        world.save_npc(target)

        # 3) Witness memories. The target's own memory carries a strong
        #    negative emotional_charge baseline — the LLM may refine it
        #    later but the raw charge is unambiguous.
        witnesses = world.witnesses_for(
            WitnessesRule.SAME_LOCATION, location_id=location_id
        )
        raw_facts: dict[str, Any] = {"offender": actor_id, "target": target_id}
        if description:
            raw_facts["description"] = description
        memory_ids = world.record_witnessed_event(
            witnesses=witnesses,
            event_type=EventType.OFFENDED,
            participants=[actor_id, target_id],
            location_id=location_id,
            raw_facts=raw_facts,
            base_importance=0.6,
            base_emotional_charge=-0.4,
            tags=["冒犯"],
        )

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
            narrative_hint=description,
        )


register_action(OffendNPC())
