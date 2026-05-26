"""NPC round-trip: pydantic <-> dict <-> DB <-> pydantic."""

from __future__ import annotations

from sqlmodel import Session

from wulin_mud.ontology import NPC
from wulin_mud.world.persistence import load_npc, save_npc


def test_npc_dict_round_trip(npc_sun: NPC) -> None:
    payload = npc_sun.model_dump()
    rebuilt = NPC.model_validate(payload)
    assert rebuilt == npc_sun


def test_npc_db_round_trip(session: Session, npc_sun: NPC) -> None:
    save_npc(session, npc_sun)
    session.commit()
    loaded = load_npc(session, npc_sun.id)
    assert loaded is not None
    assert loaded == npc_sun


def test_npc_relationships_persisted_as_edges(session: Session, npc_sun: NPC) -> None:
    save_npc(session, npc_sun)
    session.commit()
    loaded = load_npc(session, npc_sun.id)
    assert loaded is not None
    assert set(loaded.relationships.keys()) == set(npc_sun.relationships.keys())
    for other_id, rel in npc_sun.relationships.items():
        assert loaded.relationships[other_id] == rel


def test_npc_player_relationship_persisted(session: Session, npc_sun: NPC) -> None:
    save_npc(session, npc_sun)
    session.commit()
    loaded = load_npc(session, npc_sun.id)
    assert loaded is not None
    assert loaded.player_relationship == npc_sun.player_relationship
