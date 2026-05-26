"""Location round-trip."""

from __future__ import annotations

from sqlmodel import Session

from wulin_mud.ontology import Location
from wulin_mud.world.persistence import LocationRow, location_to_row, row_to_location


def test_location_dict_round_trip(location_pharmacy: Location) -> None:
    assert Location.model_validate(location_pharmacy.model_dump()) == location_pharmacy


def test_location_db_round_trip(session: Session, location_pharmacy: Location) -> None:
    session.add(location_to_row(location_pharmacy))
    session.commit()
    row = session.get(LocationRow, location_pharmacy.id)
    assert row is not None
    assert row_to_location(row) == location_pharmacy
