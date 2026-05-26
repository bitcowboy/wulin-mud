"""SQLite persistence for the Ontology.

Design:
- One SQLModel "row" class per Object Type. Nested complex types
  (Personality, Mood, SpeechStyle, Secrets, etc.) are stored as JSON
  columns so each Object Type maps to a single table.
- Relationships are stored as one-directional edges in the
  `relationships` table; bidirectional consistency is enforced at
  seed time, not at query time.
- A SQLite trigger enforces Memory.interpretation immutability at the
  storage layer — the python `__setattr__` guard catches accidental
  in-process mutation; the trigger catches any code path that writes
  via raw SQL or via model_copy() round-trips.

The row classes deliberately do not subclass the domain pydantic
models. The two layers are kept separate so the domain model stays
"clean ontology" and the row layer stays "clean storage".
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import JSON, Column
from sqlalchemy.engine import Engine
from sqlmodel import Field, Session, SQLModel, create_engine, select

from wulin_mud.ontology import (
    NPC,
    ActionRecord,
    Item,
    Location,
    Memory,
    PlayerRelationship,
    PlayerState,
    Relationship,
    Rumor,
)

# ---------------------------------------------------------------------------
# Row models
# ---------------------------------------------------------------------------


class NpcRow(SQLModel, table=True):
    __tablename__ = "npcs"

    id: str = Field(primary_key=True)
    name: str
    age: int
    gender: str
    role: str
    appearance: str | None = None
    current_location_id: str

    personality: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    background: str = ""
    secrets: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    constraints: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    speech_style: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    mood: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    health: float = 1.0
    wealth: int = 0
    energy: float = 1.0

    knowledge: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    heard_rumors: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    short_term_goals: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    long_term_goals: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))


class RelationshipRow(SQLModel, table=True):
    __tablename__ = "relationships"

    from_npc_id: str = Field(primary_key=True)
    other_id: str = Field(primary_key=True)

    affection: float
    trust: float
    familiarity: float
    relationship_type: str
    relationship_label: str

    notable_memory_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    last_interaction_at: float | None = None


class PlayerRelationshipRow(SQLModel, table=True):
    __tablename__ = "player_relationships"

    npc_id: str = Field(primary_key=True)
    other_id: str

    affection: float
    trust: float
    familiarity: float
    relationship_type: str
    relationship_label: str
    notable_memory_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    last_interaction_at: float | None = None

    first_met_at: float | None = None
    impression_summary: str = ""


class LocationRow(SQLModel, table=True):
    __tablename__ = "locations"

    id: str = Field(primary_key=True)
    name: str
    type: str
    description: str
    current_npcs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    atmosphere: str = ""
    owner_npc_id: str | None = None
    connected_to: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class ItemRow(SQLModel, table=True):
    __tablename__ = "items"

    id: str = Field(primary_key=True)
    name: str
    type: str
    description: str = ""
    base_price: int = 0
    owner_id: str | None = None
    location_id: str | None = None
    is_unique: bool = False
    item_metadata: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class RumorRow(SQLModel, table=True):
    __tablename__ = "rumors"

    id: str = Field(primary_key=True)
    created_at: float
    source_event_id: str | None = None
    original_content: str
    spread_chain: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    veracity: float
    spice_level: float


class MemoryRow(SQLModel, table=True):
    __tablename__ = "memories"

    id: str = Field(primary_key=True)
    timestamp: float
    event_type: str
    participants: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    location_id: str
    raw_facts: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    npc_id: str = Field(index=True)
    interpretation: str = ""
    emotional_charge: float = 0.0

    importance: float = 0.5
    decay_rate: float = 0.05
    last_recalled_at: float | None = None

    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    embedding: list[float] | None = Field(default=None, sa_column=Column(JSON))


class PlayerStateRow(SQLModel, table=True):
    __tablename__ = "player_state"

    id: str = Field(primary_key=True)
    current_location_id: str
    wealth: int = 0
    inventory_item_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class ActionRecordRow(SQLModel, table=True):
    __tablename__ = "action_records"

    id: str = Field(primary_key=True)
    timestamp: float
    action_type: str
    actor_id: str = Field(index=True)
    parameters: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    succeeded: bool
    side_effects_applied: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    memories_generated: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    initiated_by: str
    llm_reasoning: str | None = None


# ---------------------------------------------------------------------------
# Engine / init
# ---------------------------------------------------------------------------


DEFAULT_DB_URL = "sqlite:///./var/wulin.db"


_MEMORY_INTERPRETATION_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS memory_interpretation_immutable
BEFORE UPDATE OF interpretation ON memories
FOR EACH ROW
WHEN OLD.interpretation IS NOT NULL
     AND OLD.interpretation != ''
     AND NEW.interpretation != OLD.interpretation
BEGIN
    SELECT RAISE(ABORT, 'Memory.interpretation is write-once and cannot be modified');
END;
"""


def _resolve_db_url(db_url: str | None) -> str:
    if db_url is not None:
        return db_url
    return os.environ.get("WULIN_DB_URL", DEFAULT_DB_URL)


def _ensure_sqlite_parent_dir(db_url: str) -> None:
    """If db_url is a file-backed sqlite URL, mkdir -p its parent dir."""
    prefix = "sqlite:///"
    if not db_url.startswith(prefix):
        return
    path_part = db_url[len(prefix) :]
    if not path_part or path_part == ":memory:":
        return
    Path(path_part).parent.mkdir(parents=True, exist_ok=True)


def get_engine(db_url: str | None = None) -> Engine:
    """Create a SQLModel engine pointing at the configured database.

    `db_url` overrides the WULIN_DB_URL env var. The default
    `sqlite:///./var/wulin.db` is used if neither is set.
    """
    resolved = _resolve_db_url(db_url)
    _ensure_sqlite_parent_dir(resolved)
    return create_engine(resolved)


def init_db(engine: Engine | None = None, *, db_url: str | None = None) -> Engine:
    """Create the full schema from scratch and install immutability triggers.

    Idempotent — safe to call against an existing database; tables and
    triggers are created with IF NOT EXISTS semantics.
    """
    if engine is None:
        engine = get_engine(db_url=db_url)

    SQLModel.metadata.create_all(engine)

    # Triggers must be created via raw DDL; sqlmodel doesn't model them.
    if engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            from sqlalchemy import text

            conn.execute(text(_MEMORY_INTERPRETATION_TRIGGER))

    return engine


# ---------------------------------------------------------------------------
# Domain <-> row converters
# ---------------------------------------------------------------------------


def npc_to_row(npc: NPC) -> NpcRow:
    return NpcRow(
        id=npc.id,
        name=npc.name,
        age=npc.age,
        gender=npc.gender.value,
        role=npc.role,
        appearance=npc.appearance,
        current_location_id=npc.current_location_id,
        personality=npc.personality.model_dump(mode="json"),
        background=npc.background,
        secrets=[s.model_dump(mode="json") for s in npc.secrets],
        constraints=list(npc.constraints),
        speech_style=npc.speech_style.model_dump(mode="json"),
        mood=npc.mood.model_dump(mode="json"),
        health=npc.health,
        wealth=npc.wealth,
        energy=npc.energy,
        knowledge=[f.model_dump(mode="json") for f in npc.knowledge],
        heard_rumors=[h.model_dump(mode="json") for h in npc.heard_rumors],
        short_term_goals=[g.model_dump(mode="json") for g in npc.short_term_goals],
        long_term_goals=[g.model_dump(mode="json") for g in npc.long_term_goals],
    )


def row_to_npc(
    row: NpcRow,
    relationships: dict[str, Relationship] | None = None,
    player_relationship: PlayerRelationship | None = None,
) -> NPC:
    return NPC.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "age": row.age,
            "gender": row.gender,
            "role": row.role,
            "appearance": row.appearance,
            "current_location_id": row.current_location_id,
            "personality": row.personality,
            "background": row.background,
            "secrets": row.secrets,
            "constraints": row.constraints,
            "speech_style": row.speech_style,
            "mood": row.mood,
            "health": row.health,
            "wealth": row.wealth,
            "energy": row.energy,
            "knowledge": row.knowledge,
            "heard_rumors": row.heard_rumors,
            "short_term_goals": row.short_term_goals,
            "long_term_goals": row.long_term_goals,
            "relationships": {k: v.model_dump() for k, v in (relationships or {}).items()},
            "player_relationship": (
                player_relationship.model_dump() if player_relationship else None
            ),
        }
    )


def relationship_to_row(from_npc_id: str, rel: Relationship) -> RelationshipRow:
    return RelationshipRow(
        from_npc_id=from_npc_id,
        other_id=rel.other_id,
        affection=rel.affection,
        trust=rel.trust,
        familiarity=rel.familiarity,
        relationship_type=rel.relationship_type.value,
        relationship_label=rel.relationship_label,
        notable_memory_ids=list(rel.notable_memory_ids),
        last_interaction_at=rel.last_interaction_at,
    )


def row_to_relationship(row: RelationshipRow) -> Relationship:
    return Relationship.model_validate(
        {
            "other_id": row.other_id,
            "affection": row.affection,
            "trust": row.trust,
            "familiarity": row.familiarity,
            "relationship_type": row.relationship_type,
            "relationship_label": row.relationship_label,
            "notable_memory_ids": row.notable_memory_ids,
            "last_interaction_at": row.last_interaction_at,
        }
    )


def player_relationship_to_row(npc_id: str, pr: PlayerRelationship) -> PlayerRelationshipRow:
    return PlayerRelationshipRow(
        npc_id=npc_id,
        other_id=pr.other_id,
        affection=pr.affection,
        trust=pr.trust,
        familiarity=pr.familiarity,
        relationship_type=pr.relationship_type.value,
        relationship_label=pr.relationship_label,
        notable_memory_ids=list(pr.notable_memory_ids),
        last_interaction_at=pr.last_interaction_at,
        first_met_at=pr.first_met_at,
        impression_summary=pr.impression_summary,
    )


def row_to_player_relationship(row: PlayerRelationshipRow) -> PlayerRelationship:
    return PlayerRelationship.model_validate(
        {
            "other_id": row.other_id,
            "affection": row.affection,
            "trust": row.trust,
            "familiarity": row.familiarity,
            "relationship_type": row.relationship_type,
            "relationship_label": row.relationship_label,
            "notable_memory_ids": row.notable_memory_ids,
            "last_interaction_at": row.last_interaction_at,
            "first_met_at": row.first_met_at,
            "impression_summary": row.impression_summary,
        }
    )


def location_to_row(loc: Location) -> LocationRow:
    return LocationRow(
        id=loc.id,
        name=loc.name,
        type=loc.type.value,
        description=loc.description,
        current_npcs=list(loc.current_npcs),
        atmosphere=loc.atmosphere,
        owner_npc_id=loc.owner_npc_id,
        connected_to=list(loc.connected_to),
    )


def row_to_location(row: LocationRow) -> Location:
    return Location.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "description": row.description,
            "current_npcs": row.current_npcs,
            "atmosphere": row.atmosphere,
            "owner_npc_id": row.owner_npc_id,
            "connected_to": row.connected_to,
        }
    )


def item_to_row(item: Item) -> ItemRow:
    return ItemRow(
        id=item.id,
        name=item.name,
        type=item.type.value,
        description=item.description,
        base_price=item.base_price,
        owner_id=item.owner_id,
        location_id=item.location_id,
        is_unique=item.is_unique,
        item_metadata=dict(item.metadata),
    )


def row_to_item(row: ItemRow) -> Item:
    return Item.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "description": row.description,
            "base_price": row.base_price,
            "owner_id": row.owner_id,
            "location_id": row.location_id,
            "is_unique": row.is_unique,
            "metadata": row.item_metadata,
        }
    )


def rumor_to_row(rumor: Rumor) -> RumorRow:
    return RumorRow(
        id=rumor.id,
        created_at=rumor.created_at,
        source_event_id=rumor.source_event_id,
        original_content=rumor.original_content,
        spread_chain=[s.model_dump(mode="json") for s in rumor.spread_chain],
        veracity=rumor.veracity,
        spice_level=rumor.spice_level,
    )


def row_to_rumor(row: RumorRow) -> Rumor:
    return Rumor.model_validate(
        {
            "id": row.id,
            "created_at": row.created_at,
            "source_event_id": row.source_event_id,
            "original_content": row.original_content,
            "spread_chain": row.spread_chain,
            "veracity": row.veracity,
            "spice_level": row.spice_level,
        }
    )


def memory_to_row(memory: Memory) -> MemoryRow:
    return MemoryRow(
        id=memory.id,
        timestamp=memory.timestamp,
        event_type=memory.event_type.value,
        participants=list(memory.participants),
        location_id=memory.location_id,
        raw_facts=dict(memory.raw_facts),
        npc_id=memory.npc_id,
        interpretation=memory.interpretation,
        emotional_charge=memory.emotional_charge,
        importance=memory.importance,
        decay_rate=memory.decay_rate,
        last_recalled_at=memory.last_recalled_at,
        tags=list(memory.tags),
        embedding=list(memory.embedding) if memory.embedding else None,
    )


def row_to_memory(row: MemoryRow) -> Memory:
    return Memory.model_validate(
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "event_type": row.event_type,
            "participants": row.participants,
            "location_id": row.location_id,
            "raw_facts": row.raw_facts,
            "npc_id": row.npc_id,
            "interpretation": row.interpretation,
            "emotional_charge": row.emotional_charge,
            "importance": row.importance,
            "decay_rate": row.decay_rate,
            "last_recalled_at": row.last_recalled_at,
            "tags": row.tags,
            "embedding": row.embedding,
        }
    )


def action_record_to_row(record: ActionRecord) -> ActionRecordRow:
    return ActionRecordRow(
        id=record.id,
        timestamp=record.timestamp,
        action_type=record.action_type,
        actor_id=record.actor_id,
        parameters=dict(record.parameters),
        succeeded=record.succeeded,
        side_effects_applied=list(record.side_effects_applied),
        memories_generated=list(record.memories_generated),
        initiated_by=record.initiated_by.value,
        llm_reasoning=record.llm_reasoning,
    )


def row_to_action_record(row: ActionRecordRow) -> ActionRecord:
    return ActionRecord.model_validate(
        {
            "id": row.id,
            "timestamp": row.timestamp,
            "action_type": row.action_type,
            "actor_id": row.actor_id,
            "parameters": row.parameters,
            "succeeded": row.succeeded,
            "side_effects_applied": row.side_effects_applied,
            "memories_generated": row.memories_generated,
            "initiated_by": row.initiated_by,
            "llm_reasoning": row.llm_reasoning,
        }
    )


def player_state_to_row(state: PlayerState) -> PlayerStateRow:
    return PlayerStateRow(
        id=state.id,
        current_location_id=state.current_location_id,
        wealth=state.wealth,
        inventory_item_ids=list(state.inventory_item_ids),
    )


def row_to_player_state(row: PlayerStateRow) -> PlayerState:
    return PlayerState.model_validate(
        {
            "id": row.id,
            "current_location_id": row.current_location_id,
            "wealth": row.wealth,
            "inventory_item_ids": row.inventory_item_ids,
        }
    )


# ---------------------------------------------------------------------------
# Convenience save / load helpers
# ---------------------------------------------------------------------------


def save_npc(session: Session, npc: NPC) -> None:
    """Upsert an NPC and its relationships in one go."""
    session.merge(npc_to_row(npc))
    for other_id, rel in npc.relationships.items():
        # The rel.other_id field is the source of truth, but for robustness
        # we accept either the dict key or the field if they disagree.
        rel_for_storage = (
            rel if rel.other_id == other_id else rel.model_copy(update={"other_id": other_id})
        )
        session.merge(relationship_to_row(npc.id, rel_for_storage))
    if npc.player_relationship is not None:
        session.merge(player_relationship_to_row(npc.id, npc.player_relationship))


def load_npc(session: Session, npc_id: str) -> NPC | None:
    row = session.get(NpcRow, npc_id)
    if row is None:
        return None
    rel_rows = session.exec(
        select(RelationshipRow).where(RelationshipRow.from_npc_id == npc_id)
    ).all()
    relationships = {r.other_id: row_to_relationship(r) for r in rel_rows}
    pr_row = session.get(PlayerRelationshipRow, npc_id)
    player_relationship = row_to_player_relationship(pr_row) if pr_row else None
    return row_to_npc(row, relationships=relationships, player_relationship=player_relationship)


def list_npc_ids(session: Session) -> list[str]:
    rows = session.exec(select(NpcRow.id)).all()
    return list(rows)


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
    "action_record_to_row",
    "get_engine",
    "init_db",
    "item_to_row",
    "list_npc_ids",
    "load_npc",
    "location_to_row",
    "memory_to_row",
    "npc_to_row",
    "player_relationship_to_row",
    "player_state_to_row",
    "relationship_to_row",
    "row_to_action_record",
    "row_to_item",
    "row_to_location",
    "row_to_memory",
    "row_to_npc",
    "row_to_player_relationship",
    "row_to_player_state",
    "row_to_relationship",
    "row_to_rumor",
    "rumor_to_row",
    "save_npc",
]
