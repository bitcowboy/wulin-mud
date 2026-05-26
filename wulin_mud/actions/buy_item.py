"""BuyItem — exchange wealth for an item.

See docs/action-types.md §3.3.

Validation enforces:
- the item exists and is owned by an NPC at the actor's location
  (a vendor present in the room)
- the actor has enough wealth to cover ``price``
- ``price`` is positive and within 2× the item's base_price
  (wide sanity range; haggling lives in this band)
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
from wulin_mud.core.enums import EventType
from wulin_mud.ontology import PLAYER_ID
from wulin_mud.world.state import WorldState


class BuyItem(ActionType):
    name = "BuyItem"
    description = "购买一件物品。需要给出价格。"
    callable_by: ClassVar[set[CallerType]] = {CallerType.PLAYER, CallerType.NPC}

    def validate(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ValidationResult:
        item_id = params.get("item_id")
        price = params.get("price")

        if not isinstance(item_id, str) or not item_id:
            return ValidationResult(ok=False, reason="missing item_id")
        if not isinstance(price, int) or isinstance(price, bool):
            return ValidationResult(ok=False, reason="price must be an int")
        if price <= 0:
            return ValidationResult(ok=False, reason="price must be positive")

        item = world.get_item(item_id)
        if item is None:
            return ValidationResult(ok=False, reason=f"item {item_id!r} does not exist")
        if item.owner_id is None:
            return ValidationResult(ok=False, reason="item has no owner to buy from")
        if item.owner_id == actor_id:
            return ValidationResult(ok=False, reason="you already own this item")

        owner = world.get_npc(item.owner_id)
        if owner is None:
            return ValidationResult(ok=False, reason=f"item owner {item.owner_id!r} is not an NPC")

        try:
            actor_loc = actor_location_id(world, actor_id)
        except LookupError as exc:
            return ValidationResult(ok=False, reason=str(exc))
        if owner.current_location_id != actor_loc:
            return ValidationResult(
                ok=False,
                reason=f"vendor {owner.id} is at {owner.current_location_id}, "
                f"actor is at {actor_loc}",
            )

        if price > item.base_price * 2:
            return ValidationResult(
                ok=False,
                reason=f"price {price} exceeds 2x base_price {item.base_price}",
            )

        if actor_id == PLAYER_ID:
            player = world.get_player()
            if player is None:
                return ValidationResult(ok=False, reason="player state not initialised")
            if player.wealth < price:
                return ValidationResult(
                    ok=False,
                    reason=f"player wealth {player.wealth} insufficient for price {price}",
                )
        else:
            actor_npc = world.get_npc(actor_id)
            if actor_npc is None:
                return ValidationResult(ok=False, reason=f"actor {actor_id!r} not found")
            if actor_npc.wealth < price:
                return ValidationResult(
                    ok=False,
                    reason=f"npc wealth {actor_npc.wealth} insufficient for price {price}",
                )

        return ValidationResult(ok=True)

    def declare_side_effects(self, params: dict[str, Any]) -> SideEffectManifest:
        return SideEffectManifest(
            mutates_fields=[
                "Item.owner_id",
                "Item.location_id",
                "NPC.wealth",
                "PlayerState.wealth",
                "PlayerState.inventory_item_ids",
            ],
            witnesses_rule=WitnessesRule.SAME_LOCATION,
        )

    async def execute(
        self,
        params: dict[str, Any],
        world: WorldState,
        actor_id: str,
    ) -> ActionResult:
        item_id: str = params["item_id"]
        price: int = params["price"]

        item = world.get_item(item_id)
        assert item is not None and item.owner_id is not None
        owner = world.get_npc(item.owner_id)
        assert owner is not None
        location_id = owner.current_location_id

        side_effects: list[dict[str, Any]] = []

        # 1) Vendor receives the money.
        new_owner = owner.model_copy(update={"wealth": owner.wealth + price})
        world.save_npc(new_owner)
        side_effects.append(
            {
                "field": "NPC.wealth",
                "npc_id": owner.id,
                "from": owner.wealth,
                "to": new_owner.wealth,
            }
        )

        # 2) Actor pays + gains the item.
        if actor_id == PLAYER_ID:
            player = ensure_player(world)
            new_inventory = [*player.inventory_item_ids, item_id]
            new_player = player.model_copy(
                update={
                    "wealth": player.wealth - price,
                    "inventory_item_ids": new_inventory,
                }
            )
            world.save_player(new_player)
            side_effects.append(
                {
                    "field": "PlayerState.wealth",
                    "from": player.wealth,
                    "to": new_player.wealth,
                }
            )
            side_effects.append(
                {
                    "field": "PlayerState.inventory_item_ids",
                    "added": item_id,
                }
            )
        else:
            buyer = world.get_npc(actor_id)
            assert buyer is not None
            new_buyer = buyer.model_copy(update={"wealth": buyer.wealth - price})
            world.save_npc(new_buyer)
            side_effects.append(
                {
                    "field": "NPC.wealth",
                    "npc_id": buyer.id,
                    "from": buyer.wealth,
                    "to": new_buyer.wealth,
                }
            )

        # 3) Item changes hands.
        new_item = item.model_copy(update={"owner_id": actor_id, "location_id": None})
        world.save_item(new_item)
        side_effects.append(
            {
                "field": "Item.owner_id",
                "item_id": item_id,
                "from": item.owner_id,
                "to": actor_id,
            }
        )

        # 4) Witness memories.
        witnesses = world.witnesses_for(WitnessesRule.SAME_LOCATION, location_id=location_id)
        memory_ids = world.record_witnessed_event(
            witnesses=witnesses,
            event_type=EventType.BOUGHT,
            participants=[actor_id, owner.id],
            location_id=location_id,
            raw_facts={
                "item_id": item_id,
                "item_name": item.name,
                "price": price,
                "base_price": item.base_price,
                "buyer": actor_id,
                "seller": owner.id,
            },
            base_importance=0.3,
            base_emotional_charge=0.0,
            tags=["金钱", "买卖", item.name],
        )

        # 5) Audit.
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


register_action(BuyItem())
