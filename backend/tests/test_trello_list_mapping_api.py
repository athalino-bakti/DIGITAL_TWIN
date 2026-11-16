"""DIG-120: endpoint pemetaan list Trello ke status dan phase (PostgreSQL)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text

from app.modules.data.staging_models import StagingTrelloAction, TrelloListMapping
from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB

URL = "/api/v1/data/trello-lists"
BOARD = "b" * 24
OTHER_BOARD = "c" * 24
TODO, DOING, DONE = "1" * 24, "2" * 24, "3" * 24


def action(n: int, before: str | None, after: str | None, day: int, board: str = BOARD) -> dict:
    return {
        "action_id": f"{n:024x}",
        "action_type": "updateCard",
        "action_date": datetime(2026, 3, day, 9, tzinfo=UTC),
        "board_id": board,
        "card_id": "d" * 24,
        "card_name": "TSK-0001 Form cuti",
        "list_before_id": before,
        "list_after_id": after,
        "raw": {"data": {"board": {"name": "PuTI Sprint" if board == BOARD else "Lain"}}},
    }


@pytest.fixture(autouse=True)
def clean(db):
    # Tabel staging tidak ikut di-TRUNCATE conftest.
    db.execute(text("TRUNCATE staging_trello_action, trello_list_mapping, event_log"))
    db.commit()


@pytest.fixture
def lists(db):
    db.add_all(
        [
            TrelloListMapping(board_id=BOARD, list_id=TODO, list_name="To Do"),
            TrelloListMapping(board_id=BOARD, list_id=DOING, list_name="Doing"),
            TrelloListMapping(
                board_id=BOARD, list_id=DONE, list_name="Done", status="done", phase="testing"
            ),
            TrelloListMapping(board_id=OTHER_BOARD, list_id=TODO, list_name="Backlog"),
        ]
    )
    db.add_all(
        StagingTrelloAction(**a)
        for a in [
            action(1, TODO, DOING, 2),
            action(2, DOING, DONE, 5),
            action(3, None, DOING, 3),
            # Papan lain dengan id list yang sama tidak boleh ikut terhitung.
            action(4, None, TODO, 9, board=OTHER_BOARD),
        ]
    )
    db.commit()


def by_list(rows):
    return {(r["board_id"], r["list_id"]): r for r in rows}


def test_list_with_usage_and_board_name(client, lists):
    response = client.get(URL)
    assert response.status_code == 200, response.text
    rows = response.json()
    assert [r["list_name"] for r in rows] == ["Doing", "Done", "To Do", "Backlog"]
    found = by_list(rows)
    doing = found[(BOARD, DOING)]
    assert (doing["actions"], doing["last_seen"][:10]) == (3, "2026-03-05")
    assert doing["board_name"] == "PuTI Sprint"
    assert (doing["status"], doing["phase"]) == (None, None)
    assert found[(BOARD, TODO)]["actions"] == 1
    assert found[(OTHER_BOARD, TODO)]["actions"] == 1
    assert found[(BOARD, DONE)]["status"] == "done"


def test_unmapped_only(client, lists):
    rows = client.get(URL, params={"unmapped_only": True}).json()
    assert {r["list_name"] for r in rows} == {"To Do", "Doing", "Backlog"}


def test_list_without_actions(client, db):
    db.add(TrelloListMapping(board_id=BOARD, list_id=TODO, list_name="Kosong"))
    db.commit()
    [row] = client.get(URL).json()
    assert (row["actions"], row["last_seen"], row["board_name"]) == (0, None, None)


def test_update_status_and_phase(client, db, lists):
    response = client.patch(f"{URL}/{BOARD}/{DOING}", json={"status": "in_progress"})
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["phase"]) == ("in_progress", None)
    assert response.json()["actions"] == 3

    response = client.patch(f"{URL}/{BOARD}/{DOING}", json={"phase": "be_dev"})
    assert (response.json()["status"], response.json()["phase"]) == ("in_progress", "be_dev")

    # null mengosongkan pemetaan; list lain dan papan lain tidak tersentuh.
    response = client.patch(f"{URL}/{BOARD}/{DONE}", json={"status": None})
    assert (response.json()["status"], response.json()["phase"]) == (None, "testing")
    db.expire_all()
    other = db.scalar(select(TrelloListMapping).where(TrelloListMapping.board_id == OTHER_BOARD))
    assert other.status is None


def test_update_rejects_unknown_values(client, lists):
    response = client.patch(f"{URL}/{BOARD}/{DOING}", json={"status": "selesai"})
    assert response.status_code == 422
    response = client.patch(f"{URL}/{BOARD}/{DOING}", json={"list_name": "Baru"})
    assert response.status_code == 422
    assert client.patch(f"{URL}/{BOARD}/BUKAN-ID", json={}).status_code == 422


def test_update_unknown_list_is_404(client, lists):
    response = client.patch(f"{URL}/{BOARD}/{'9' * 24}", json={"status": "done"})
    assert response.status_code == 404
    assert response.json()["detail"] == "List Trello tidak ditemukan"


def test_mapping_feeds_the_event_log(client, lists):
    client.patch(f"{URL}/{BOARD}/{DOING}", json={"status": "in_progress"})
    report = client.post("/api/v1/data/event-log/rebuild")
    assert report.status_code == 200, report.text
    activities = {e["activity"] for e in client.get("/api/v1/data/event-log").json()}
    assert any("in_progress" in a or "Dikerjakan" in a for a in activities), activities
