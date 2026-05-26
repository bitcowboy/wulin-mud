"""Rumor round-trip."""

from __future__ import annotations

from sqlmodel import Session

from wulin_mud.ontology import Rumor
from wulin_mud.world.persistence import RumorRow, row_to_rumor, rumor_to_row


def test_rumor_dict_round_trip(rumor_jianghu: Rumor) -> None:
    assert Rumor.model_validate(rumor_jianghu.model_dump()) == rumor_jianghu


def test_rumor_db_round_trip(session: Session, rumor_jianghu: Rumor) -> None:
    session.add(rumor_to_row(rumor_jianghu))
    session.commit()
    row = session.get(RumorRow, rumor_jianghu.id)
    assert row is not None
    assert row_to_rumor(row) == rumor_jianghu
