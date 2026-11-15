"""DIG-117 dan DIG-118: tabel staging Trello dan penyimpanannya di PostgreSQL sungguhan.

Fixture database (`db`) dan syarat `TEST_DATABASE_URL` ada di conftest.py.
"""

import copy
import json
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.integrations.trello.parser import parse_board_export
from app.modules.data.trello_staging import save_trello_import
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


# --- save_trello_import (DIG-118) ---

FIXTURE = Path(__file__).parent / "fixtures" / "trello_board_kecil.json"


@pytest.fixture
def board() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def count(db, table: str) -> int:
    return db.execute(text(f"SELECT count(*) FROM {table}")).scalar()


def test_reimport_does_not_duplicate_actions(clean_db, board):
    result = parse_board_export(board)

    first = save_trello_import(clean_db, result)
    second = save_trello_import(clean_db, result)

    assert (first.inserted, first.already_present) == (16, 0)
    assert (second.inserted, second.already_present) == (0, 16)
    assert count(clean_db, "staging_trello_action") == 16
    assert count(clean_db, "trello_list_mapping") == 8


def test_saved_row_keeps_raw_action_and_utc_time(clean_db, board):
    result = parse_board_export(board)
    save_trello_import(clean_db, result)
    source = result.actions[0]

    saved = clean_db.execute(
        text("SELECT action_date, raw FROM staging_trello_action WHERE action_id = :id"),
        {"id": source["action_id"]},
    ).one()
    assert saved.action_date == source["action_date"]
    assert saved.raw == source["raw"]


def test_reimport_updates_list_name_but_keeps_mapping(clean_db, board):
    save_trello_import(clean_db, parse_board_export(board))
    list_id = board["lists"][0]["id"]
    clean_db.execute(
        text(
            "UPDATE trello_list_mapping SET status = 'not_started', phase = 'planning'"
            " WHERE list_id = :id"
        ),
        {"id": list_id},
    )

    renamed = copy.deepcopy(board)
    renamed["lists"][0]["name"] = "Antrian"
    save_trello_import(clean_db, parse_board_export(renamed))

    row = clean_db.execute(
        text("SELECT list_name, status, phase FROM trello_list_mapping WHERE list_id = :id"),
        {"id": list_id},
    ).one()
    assert tuple(row) == ("Antrian", "not_started", "planning")
