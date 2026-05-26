"""Internal helpers shared by the v0.1 Action implementations.

Kept private (single leading underscore) so they don't leak out as
part of the public ACTION layer surface.
"""

from __future__ import annotations

from wulin_mud.core.enums import RelationshipType
from wulin_mud.ontology import NPC, PLAYER_ID, PlayerRelationship, PlayerState, Relationship
from wulin_mud.world.state import WorldState


class ActorLocationLookupError(LookupError):
    """Raised when an actor's location cannot be resolved."""


def actor_location_id(world: WorldState, actor_id: str) -> str:
    """Resolve the current location of either the player or an NPC."""
    if actor_id == PLAYER_ID:
        player = world.get_player()
        if player is None:
            raise ActorLocationLookupError(
                "Player state is not initialised; seed it before running actions."
            )
        return player.current_location_id
    npc = world.get_npc(actor_id)
    if npc is None:
        raise ActorLocationLookupError(f"NPC {actor_id!r} not found")
    return npc.current_location_id


def ensure_relationship(npc: NPC, other_id: str) -> Relationship:
    """Return ``npc.relationships[other_id]``, creating a STRANGER stub if absent.

    Mutates ``npc.relationships`` in place. The caller is responsible
    for persisting via ``world.save_npc(npc)``.
    """
    rel = npc.relationships.get(other_id)
    if rel is None:
        rel = Relationship(
            other_id=other_id,
            affection=0.0,
            trust=0.0,
            familiarity=0.0,
            relationship_type=RelationshipType.STRANGER,
            relationship_label="陌生人",
        )
        npc.relationships[other_id] = rel
    return rel


def ensure_player_relationship(npc: NPC, *, first_met_at: float) -> PlayerRelationship:
    """Return ``npc.player_relationship``, creating it on first contact."""
    pr = npc.player_relationship
    if pr is None:
        pr = PlayerRelationship(
            other_id=PLAYER_ID,
            affection=0.0,
            trust=0.0,
            familiarity=0.0,
            relationship_type=RelationshipType.STRANGER,
            relationship_label="外来人",
            first_met_at=first_met_at,
            impression_summary="",
        )
        npc.player_relationship = pr
    return pr


def clamp(value: float, *, low: float, high: float) -> float:
    return max(low, min(high, value))


def ensure_player(world: WorldState) -> PlayerState:
    """Get the player or raise — used by actions where player state is required."""
    player = world.get_player()
    if player is None:
        raise ActorLocationLookupError("Player state is not initialised.")
    return player
