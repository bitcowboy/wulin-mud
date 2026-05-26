"""ActionRecord round-trip."""

from __future__ import annotations

from sqlmodel import Session

from wulin_mud.ontology import ActionRecord
from wulin_mud.world.persistence import (
    ActionRecordRow,
    action_record_to_row,
    row_to_action_record,
)


def test_action_record_dict_round_trip(action_record_buy: ActionRecord) -> None:
    assert ActionRecord.model_validate(action_record_buy.model_dump()) == action_record_buy


def test_action_record_db_round_trip(session: Session, action_record_buy: ActionRecord) -> None:
    session.add(action_record_to_row(action_record_buy))
    session.commit()
    row = session.get(ActionRecordRow, action_record_buy.id)
    assert row is not None
    assert row_to_action_record(row) == action_record_buy
