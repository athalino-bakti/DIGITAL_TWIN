"""DIG-221: aturan tanggal change_event_details (DATA_CONTRACT 7.3) di validator J&C."""

from datetime import date

import pytest
from sqlalchemy import text

from app.modules.data.change_event_detail_rules import (
    check_detail_dates,
    check_event_date_change,
    validate_detail,
)
from app.modules.data.service import DataValidationError
from tests.conftest import REQUIRES_DB

EVENT = date(2026, 9, 10)


def fields(errors) -> list[str]:
    return [error.field for error in errors]


@pytest.mark.parametrize(
    "approved,resolved",
    [
        (None, None),
        (EVENT, EVENT),
        (date(2026, 9, 11), date(2026, 10, 1)),
        (None, date(2026, 9, 10)),
    ],
)
def test_dates_on_or_after_event_date_pass(approved, resolved):
    assert check_detail_dates(EVENT, approved, resolved) == []


@pytest.mark.parametrize(
    "approved,resolved,expected",
    [
        (date(2026, 9, 9), None, ["approved_date"]),
        (None, date(2026, 9, 1), ["resolved_date"]),
        (date(2026, 9, 9), date(2026, 9, 9), ["approved_date", "resolved_date"]),
    ],
)
def test_dates_before_event_date_are_reported_per_column(approved, resolved, expected):
    errors = check_detail_dates(EVENT, approved, resolved)
    assert fields(errors) == expected
    assert all(e.error_type == "before_event_date" for e in errors)
    assert all("2026-09-10" in e.message for e in errors)


# --- terhadap basis data ---------------------------------------------------------------------


@pytest.fixture
def event(client, db):
    from tests.test_support_tables import add_event

    return add_event(client, db, event_date=EVENT.isoformat())


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_validate_detail_reads_event_date(event, db):
    validate_detail(db, {"event_id": event, "approved_date": EVENT, "resolved_date": None})
    with pytest.raises(DataValidationError) as caught:
        validate_detail(db, {"event_id": event, "resolved_date": date(2026, 9, 1)})
    assert fields(caught.value.errors) == ["resolved_date"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_validate_detail_rejects_unknown_event(client, db):
    with pytest.raises(DataValidationError) as caught:
        validate_detail(db, {"event_id": "EVT-999", "approved_date": EVENT})
    assert fields(caught.value.errors) == ["event_id"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_moving_event_date_past_detail_dates_is_reported(event, db):
    assert check_event_date_change(db, event, date(2026, 12, 1)) == []  # belum ada detail

    db.execute(
        text(
            "INSERT INTO change_event_details (event_id, approved_date, resolved_date) "
            "VALUES (:e, '2026-09-12', '2026-09-20')"
        ),
        {"e": event},
    )
    db.commit()
    assert check_event_date_change(db, event, date(2026, 9, 1)) == []
    assert check_event_date_change(db, event, date(2026, 9, 12)) == []
    errors = check_event_date_change(db, event, date(2026, 9, 13))
    assert fields(errors) == ["event_date"]
    assert "2026-09-12" in errors[0].message
