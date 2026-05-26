"""World-state runtime: persistence, world tick, and seed loading.

Currently only persistence is implemented (see docs/roadmap.md
v0.1 Day 2-4). World tick and the in-memory WorldState facade arrive
in later sprints.
"""

from wulin_mud.world.persistence import (
    DEFAULT_DB_URL,
    ActionRecordRow,
    ItemRow,
    LocationRow,
    MemoryRow,
    NpcRow,
    PlayerRelationshipRow,
    RelationshipRow,
    RumorRow,
    get_engine,
    init_db,
    list_npc_ids,
    load_npc,
    save_npc,
)

__all__ = [
    "ActionRecordRow",
    "DEFAULT_DB_URL",
    "ItemRow",
    "LocationRow",
    "MemoryRow",
    "NpcRow",
    "PlayerRelationshipRow",
    "RelationshipRow",
    "RumorRow",
    "get_engine",
    "init_db",
    "list_npc_ids",
    "load_npc",
    "save_npc",
]
