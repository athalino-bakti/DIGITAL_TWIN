"""DIG-164: constraint tabel event_log terhadap PostgreSQL sungguhan."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import REQUIRES_DB
from tests.test_resources_api import create as create_member

pytestmark = REQUIRES_DB

INSERT = text(
    "INSERT INTO event_log (case_id, activity, activity_kind, event_time, resource_id, "
    "source, source_ref) VALUES (:case, 'Task dibuat', :kind, '2026-09-01T09:00:00+07:00', "
    ":resource, :source, :ref)"
)


def row(**overrides) -> dict:
    return {
        "case": "TSK-0001",
        "kind": "created",
        "resource": None,
        "source": "trello",
        "ref": "a" * 24,
    } | overrides


@pytest.fixture
def empty_log(client, db):
    db.execute(text("TRUNCATE event_log RESTART IDENTITY"))
    db.commit()
    yield
    db.execute(text("TRUNCATE event_log RESTART IDENTITY"))
    db.commit()


def violated(db, params) -> str | None:
    with pytest.raises(IntegrityError) as caught:
        db.execute(INSERT, params)
        db.flush()
    db.rollback()
    return caught.value.orig.diag.constraint_name


def test_valid_event_is_stored(empty_log, db):
    db.execute(INSERT, row())
    db.commit()
    assert db.scalar(text("SELECT count(*) FROM event_log")) == 1


@pytest.mark.parametrize(
    "overrides,constraint",
    [
        ({"kind": "moved"}, "ck_event_log_activity_kind_valid"),
        ({"source": "jira"}, "ck_event_log_source_valid"),
        ({"resource": "RES-999"}, "fk_event_log_resource_id_resources"),
    ],
)
def test_invalid_values_are_rejected(empty_log, db, overrides, constraint):
    assert violated(db, row(**overrides)) == constraint


def test_one_event_per_source_row(empty_log, db):
    db.execute(INSERT, row())
    db.commit()
    assert violated(db, row(case="TSK-0002")) == "uq_event_log_source_source_ref"
    # Ref yang sama dari sumber lain tetap boleh.
    db.execute(INSERT, row(source="change_event"))
    db.commit()


def test_deleting_member_keeps_event_without_resource(empty_log, client, db):
    rid = create_member(client)["resource_id"]
    db.execute(INSERT, row(resource=rid))
    db.commit()
    assert client.delete(f"/api/v1/data/resources/{rid}").status_code == 204
    db.expire_all()
    assert db.execute(text("SELECT resource_id FROM event_log")).scalar_one() is None
