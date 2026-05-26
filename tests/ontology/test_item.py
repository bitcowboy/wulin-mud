"""Item round-trip."""

from __future__ import annotations

from sqlmodel import Session

from wulin_mud.ontology import Item
from wulin_mud.world.persistence import ItemRow, item_to_row, row_to_item


def test_item_dict_round_trip(item_zhixue_gao: Item) -> None:
    assert Item.model_validate(item_zhixue_gao.model_dump()) == item_zhixue_gao


def test_item_db_round_trip(session: Session, item_zhixue_gao: Item) -> None:
    session.add(item_to_row(item_zhixue_gao))
    session.commit()
    row = session.get(ItemRow, item_zhixue_gao.id)
    assert row is not None
    assert row_to_item(row) == item_zhixue_gao
