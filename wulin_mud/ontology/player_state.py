"""PlayerState Object Type.

The player has no rich Ontology presence in v0.1 (no personality, no
relationships from their side, no memories). But several Actions need
to read or mutate basic state about them — most obviously BuyItem
(wealth + inventory) and MoveTo (location).

This minimal model is what lets the Action layer treat the player
symmetrically with NPCs for those few concerns, without pretending the
player is a full NPC.

The player's actor id throughout the codebase is the literal string
``"player"`` (matches the id of this row).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

PLAYER_ID = "player"


class PlayerState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = PLAYER_ID
    current_location_id: str
    wealth: int = Field(default=0, ge=0)
    inventory_item_ids: list[str] = Field(default_factory=list)
