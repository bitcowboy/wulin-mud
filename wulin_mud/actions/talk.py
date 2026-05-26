"""Talk — the milestone action.

A Talk turn:

1. Retrieves the target NPC's top-N memories about the player + last
   few dialogue turns.
2. Asks the LLM to generate the NPC's in-character reply.
3. Persists a single TALKED Memory for the target whose ``raw_facts``
   capture both sides of the exchange — the same row that the
   interpretation generator then reads to write the NPC's first-person
   read of the conversation.
4. Bumps familiarity (smaller than Greet — talking continues an
   established interaction rather than initiating one).
5. Returns the reply via ``ActionResult.narrative_hint`` for the
   consumption layer to render.

The reply itself is generated through the same LLM provider used for
the interpretation. That keeps the entire LLM surface area inside
``wulin_mud/llm/`` and respects the "LLM never writes world state"
red line: the provider produces strings; only ``record_witnessed_event``
writes to the DB.
"""

from __future__ import annotations

from typing import Any, ClassVar

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
from wulin_mud.llm.dialogue import generate_dialogue
from wulin_mud.ontology import PLAYER_ID
from wulin_mud.world.state import WorldState

_FAMILIARITY_INCREMENT = 0.02
_MEMORY_TOP_N = 10
_DIALOGUE_MAX_TURNS = 6


class Talk(ActionType):
    name = "Talk"
    description = "和某个 NPC 自由对话。LLM 用该 NPC 的人设生成回应。"
    callable_by: ClassVar[set[CallerType]] = {CallerType.PLAYER, CallerType.NPC}

    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        target_id = params.get("target_id")
        content = params.get("content")
        if not isinstance(target_id, str) or not target_id:
            return ValidationResult(ok=False, reason="missing target_id")
        if target_id == actor_id:
            return ValidationResult(ok=False, reason="cannot talk to yourself")
        if not isinstance(content, str) or not content.strip():
            return ValidationResult(ok=False, reason="content must be a non-empty string")

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

        if world.llm is None:
            return ValidationResult(
                ok=False,
                reason="Talk requires an LLM provider — none was attached to the executor",
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
        content: str = params["content"].strip()
        target = world.get_npc(target_id)
        assert target is not None  # guaranteed by validate()
        location_id = target.current_location_id

        side_effects: list[dict[str, Any]] = []

        # ----- 1. Gather retrieval context -----
        relevant_memories = world.retrieve_relevant_memories(target_id, top_n=_MEMORY_TOP_N)
        recent_dialogue = world.retrieve_recent_dialogue(
            target_id, with_actor_id=actor_id, max_turns=_DIALOGUE_MAX_TURNS
        )

        # ----- 2. Generate the NPC's reply -----
        assert world.llm is not None  # validate() guarantees this
        reply = await generate_dialogue(
            provider=world.llm,
            npc=target,
            actor_id=actor_id,
            player_input=content,
            relevant_memories=relevant_memories,
            recent_dialogue=recent_dialogue,
        )

        # ----- 3. Bump familiarity -----
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

        # ----- 4. Record the exchange. Only the target NPC's Memory
        # captures the full text; other witnesses just see "X spoke to Y". -----
        target_memory_ids = await world.record_witnessed_event(
            witnesses=[target_id],
            event_type=EventType.TALKED,
            participants=[actor_id, target_id],
            location_id=location_id,
            raw_facts={
                "speaker": actor_id,
                "listener": target_id,
                "said": content,
                "replied": reply,
            },
            base_importance=0.3,
            base_emotional_charge=0.0,
            tags=["对话"],
        )

        # Bystanders (NPCs in the room other than the target) get a thinner
        # Memory: same event, no transcribed dialogue.
        bystander_ids = [
            w
            for w in world.witnesses_for(WitnessesRule.SAME_LOCATION, location_id=location_id)
            if w != target_id
        ]
        bystander_memory_ids = await world.record_witnessed_event(
            witnesses=bystander_ids,
            event_type=EventType.TALKED,
            participants=[actor_id, target_id],
            location_id=location_id,
            raw_facts={"speaker": actor_id, "listener": target_id},
            base_importance=0.1,
            base_emotional_charge=0.0,
            tags=["对话", "旁观"],
        )

        memory_ids = [*target_memory_ids, *bystander_memory_ids]

        # ----- 5. Bump last_recalled_at on memories that fed the prompt
        # — they were "remembered" right now, which delays decay. -----
        world.mark_memories_recalled(m.id for m in relevant_memories)
        world.mark_memories_recalled(m.id for m in recent_dialogue)

        # ----- 6. Audit -----
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
            narrative_hint=reply,
        )


register_action(Talk())
