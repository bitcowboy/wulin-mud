"""World-state runtime: persistence, world tick, and seed loading.

Day 2-4 added the SQLite persistence layer.
Day 4-7 adds the WorldState facade used by Actions.
World tick scheduling lands in a later sprint.
"""

from wulin_mud.world.persistence import (
    DEFAULT_DB_URL,
    ActionRecordRow,
    ItemRow,
    LocationRow,
    MemoryRow,
    NpcRow,
    PlayerRelationshipRow,
    PlayerStateRow,
    RelationshipRow,
    RumorRow,
    get_engine,
    init_db,
    list_npc_ids,
    load_npc,
    save_npc,
)
from wulin_mud.world.state import WorldState

__all__ = [
    "DEFAULT_DB_URL",
    "ActionRecordRow",
    "ItemRow",
    "LocationRow",
    "MemoryRow",
    "NpcRow",
    "PlayerRelationshipRow",
    "PlayerStateRow",
    "RelationshipRow",
    "RumorRow",
    "WorldState",
    "get_engine",
    "init_db",
    "list_npc_ids",
    "load_npc",
    "save_npc",
]
