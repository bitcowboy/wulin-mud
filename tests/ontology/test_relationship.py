"""Relationship + PlayerRelationship round-trips at all four layers."""

from __future__ import annotations

from sqlmodel import Session, select

from wulin_mud.core.enums import RelationshipType
from wulin_mud.ontology import PlayerRelationship, Relationship
from wulin_mud.world.persistence import (
    PlayerRelationshipRow,
    RelationshipRow,
    player_relationship_to_row,
    relationship_to_row,
    row_to_player_relationship,
    row_to_relationship,
)


def _make_relationship() -> Relationship:
    return Relationship(
        other_id="npc_other",
        affection=0.3,
        trust=0.4,
        familiarity=0.5,
        relationship_type=RelationshipType.OLD_ACQUAINTANCE,
        relationship_label="旧识",
        notable_memory_ids=["mem_001", "mem_002"],
        last_interaction_at=4242.0,
    )


def _make_player_relationship() -> PlayerRelationship:
    return PlayerRelationship(
        other_id="player",
        affection=-0.1,
        trust=0.2,
        familiarity=0.3,
        relationship_type=RelationshipType.STRANGER,
        relationship_label="外人",
        first_met_at=10.0,
        impression_summary="还看不准",
    )


def test_relationship_dict_round_trip() -> None:
    rel = _make_relationship()
    assert Relationship.model_validate(rel.model_dump()) == rel


def test_relationship_db_round_trip(session: Session) -> None:
    rel = _make_relationship()
    session.add(relationship_to_row("npc_self", rel))
    session.commit()
    row = session.exec(
        select(RelationshipRow).where(
            RelationshipRow.from_npc_id == "npc_self",
            RelationshipRow.other_id == "npc_other",
        )
    ).one()
    assert row_to_relationship(row) == rel


def test_player_relationship_dict_round_trip() -> None:
    pr = _make_player_relationship()
    assert PlayerRelationship.model_validate(pr.model_dump()) == pr


def test_player_relationship_db_round_trip(session: Session) -> None:
    pr = _make_player_relationship()
    session.add(player_relationship_to_row("npc_self", pr))
    session.commit()
    row = session.get(PlayerRelationshipRow, "npc_self")
    assert row is not None
    assert row_to_player_relationship(row) == pr
