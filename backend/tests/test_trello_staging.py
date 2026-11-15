"""DIG-117: aturan tabel staging_trello_action dan trello_list_mapping di PostgreSQL sungguhan.

Fixture database (`db`) dan syarat `TEST_DATABASE_URL` ada di conftest.py.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB

BOARD = "b" * 24
LIST = "1" * 24


@pytest.fixture
def clean_db(db):
    db.execute(text("TRUNCATE staging_trello_action, trello_list_mapping"))
    db.commit()
    yield db
    db.rollback()


def insert_action(db, action_id: str) -> None:
    db.execute(
        text(
            "INSERT INTO staging_trello_action (action_id, action_type, action_date, board_id, raw)"
            " VALUES (:id, 'createCard', '2026-10-01T01:00:00Z', :board, '{}'::jsonb)"
        ),
        {"id": action_id, "board": BOARD},
    )
    db.flush()


def insert_mapping(db, **values) -> None:
    db.execute(
        text(
            "INSERT INTO trello_list_mapping (board_id, list_id, list_name, status, phase)"
            " VALUES (:board, :list, 'Done', :status, :phase)"
        ),
        {"board": BOARD, "list": LIST, "status": None, "phase": None} | values,
    )
    db.flush()


def test_action_id_must_be_trello_id(clean_db):
    insert_action(clean_db, "a" * 24)
    with pytest.raises(IntegrityError, match="ck_staging_trello_action_action_id_format"):
        insert_action(clean_db, "BUKAN-ID-TRELLO")


def test_action_id_is_unique(clean_db):
    insert_action(clean_db, "a" * 24)
    with pytest.raises(IntegrityError, match="pk_staging_trello_action"):
        insert_action(clean_db, "a" * 24)


def test_list_mapping_accepts_unmapped_and_task_enums(clean_db):
    insert_mapping(clean_db)
    insert_mapping(clean_db, list="2" * 24, status="done", phase="testing")
    count = clean_db.execute(text("SELECT count(*) FROM trello_list_mapping")).scalar()
    assert count == 2


@pytest.mark.parametrize(
    ("values", "constraint"),
    [
        ({"status": "selesai"}, "ck_trello_list_mapping_status_valid"),
        ({"phase": "deploy"}, "ck_trello_list_mapping_phase_valid"),
    ],
)
def test_list_mapping_rejects_values_outside_task_enums(clean_db, values, constraint):
    with pytest.raises(IntegrityError, match=constraint):
        insert_mapping(clean_db, **values)


def test_list_mapping_is_unique_per_board_and_list(clean_db):
    insert_mapping(clean_db)
    with pytest.raises(IntegrityError, match="pk_trello_list_mapping"):
        insert_mapping(clean_db)
