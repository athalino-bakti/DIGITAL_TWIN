"""DIG-166: urutan dan kelengkapan event log dari data sintetis seed 42 (PostgreSQL sungguhan).

Papan Trello sintetis dimuat lewat jalur impor yang sama dengan aplikasi (parser DIG-118 lalu
staging DIG-117). Projects, resources, tasks, dan change_events dimuat dari final sources dunia
simulasi yang sama, sehingga setiap kartu TSK punya task di D-05.
"""

import copy
from collections import Counter, defaultdict
from datetime import date

import pytest
from sqlalchemy import insert, text

from app.db.base import Base
from app.integrations.trello.parser import parse_board_export
from app.modules.data.event_log import WIB, list_event_log, rebuild_event_log
from app.modules.data.trello_staging import save_trello_import
from synthetic.final_sources import final_source_rows
from synthetic.raw_sources import trello_board
from synthetic.world import build_world
from tests.conftest import REQUIRES_DB, make_token

pytestmark = REQUIRES_DB

AS_OF = date(2026, 11, 6)
URL = "/api/v1/data/event-log"


@pytest.fixture(scope="module")
def world():
    return build_world(42, AS_OF)


@pytest.fixture(scope="module")
def board(world):
    return trello_board(world)


def code_of(card: dict) -> str:
    return card["name"].split(" | ")[0]


def load(db, world, board) -> None:
    db.execute(text("TRUNCATE staging_trello_action, trello_list_mapping, event_log"))
    rows = final_source_rows(world)
    for table in ("projects", "resources", "tasks", "change_events"):
        db.execute(insert(Base.metadata.tables[table]), rows[table])
    save_trello_import(db, parse_board_export(board))
    db.commit()


@pytest.fixture
def loaded(client, db, world, board):
    load(db, world, board)
    return rebuild_event_log(db)


def expected_kinds(board: dict, world) -> Counter:
    task_cards = {c["id"] for c in board["cards"] if code_of(c).startswith("TSK-")}
    kinds: Counter = Counter()
    for a in board["actions"]:
        if a["data"]["card"]["id"] not in task_cards:
            continue
        if a["type"] == "createCard":
            kinds["created"] += 1
        elif a["type"] in ("addMemberToCard", "removeMemberFromCard"):
            kinds["assignment"] += 1
        elif "listAfter" in a["data"]:
            kinds["status"] += 1
        elif (a["data"].get("old") or {}).get("closed") is False:
            kinds["archived"] += 1
    kinds["change_event"] = sum(1 for e in world.events if e.affected_task_id)
    return kinds


def events_by_case(db) -> dict[str, list]:
    cases = defaultdict(list)
    for event in list_event_log(db):
        cases[event.case_id].append(event)
    return cases


# --- kelengkapan --------------------------------------------------------------------------------


def test_every_task_card_becomes_one_case(loaded, db, board):
    task_codes = {code_of(c) for c in board["cards"] if code_of(c).startswith("TSK-")}
    assert set(events_by_case(db)) == task_codes
    assert loaded.cases == len(task_codes)
    assert loaded.cases_not_in_tasks == 0


def test_event_counts_match_source_actions(loaded, db, board, world):
    expected = expected_kinds(board, world)
    assert Counter(loaded.by_kind) == expected
    assert loaded.events == sum(expected.values())
    stored = Counter(
        dict(db.execute(text("SELECT activity_kind, count(*) FROM event_log GROUP BY 1")).all())
    )
    assert stored == expected


def test_skipped_rows_are_reported_per_reason(loaded, board, world):
    wli_cards = {c["id"] for c in board["cards"] if code_of(c).startswith("WLI-")}
    wli_actions = sum(1 for a in board["actions"] if a["data"]["card"]["id"] in wli_cards)
    assert loaded.skipped["kartu_beban_non_proyek"] == wli_actions
    assert loaded.skipped["change_event_tanpa_task"] == sum(
        1 for e in world.events if not e.affected_task_id
    )


# --- urutan -------------------------------------------------------------------------------------


def test_each_case_starts_with_task_created(loaded, db):
    for case, events in events_by_case(db).items():
        trello = [e for e in events if e.source == "trello"]
        assert trello[0].activity == "Task dibuat", case
        # Bukan menang urutan event_id: pembuatan kartu benar-benar paling awal (DIG-225).
        assert len(trello) == 1 or trello[0].event_time < trello[1].event_time, case


def test_events_are_ordered_by_time_within_each_case(loaded, db):
    for case, events in events_by_case(db).items():
        times = [e.event_time for e in events]
        assert times == sorted(times), case


def test_list_moves_follow_each_other(loaded, db):
    """List tujuan setiap perpindahan sama dengan list awal perpindahan berikutnya."""
    rows = db.execute(
        text(
            "SELECT e.case_id, s.list_before_name, s.list_after_name FROM event_log e "
            "JOIN staging_trello_action s ON s.action_id = e.source_ref "
            "WHERE e.activity_kind = 'status' ORDER BY e.case_id, e.event_time, e.event_id"
        )
    ).all()
    position: dict[str, str] = {}
    for case, before, after in rows:
        if case in position:
            assert before == position[case], case
        position[case] = after


# --- bangun ulang, filter, pelaku ---------------------------------------------------------------


def test_rebuild_is_idempotent(loaded, db):
    again = rebuild_event_log(db)
    assert (again.events, again.cases, again.by_kind) == (
        loaded.events,
        loaded.cases,
        loaded.by_kind,
    )
    assert db.scalar(text("SELECT count(*) FROM event_log")) == loaded.events


def test_filters_by_project_and_inclusive_dates(loaded, db, world):
    project = world.projects[0].project_id
    tasks = {t.task_id for t in world.tasks if t.project_id == project}
    events = list_event_log(db, project_id=project)
    assert events and {e.case_id for e in events} <= tasks

    first = min(e.event_time for e in events)
    day = first.astimezone(WIB).date()
    same_day = list_event_log(db, project_id=project, date_from=day, date_to=day)
    assert same_day and all(e.event_time.astimezone(WIB).date() == day for e in same_day)


def test_resource_waits_for_alias_but_actor_is_kept(loaded, db, board):
    assert loaded.events_without_resource == loaded.events
    usernames = {m["username"] for m in board["members"]}
    trello_actors = {e.actor_name for e in list_event_log(db) if e.source == "trello"}
    assert trello_actors and trello_actors <= usernames | {m["fullName"] for m in board["members"]}


def test_mapped_list_renames_status_activity(loaded, db):
    db.execute(
        text(
            "UPDATE trello_list_mapping SET status = 'in_progress' WHERE list_name = 'In Progress'"
        )
    )
    db.commit()
    rebuild_event_log(db)
    activities = {e.activity for e in list_event_log(db) if e.activity_kind == "status"}
    assert "in_progress" in activities and "In Progress" not in activities


def test_cards_without_task_code_are_reported(client, db, world, board):
    dirty = copy.deepcopy(board)
    renamed = [c for c in dirty["cards"] if code_of(c).startswith("TSK-")][:2]
    for card in renamed:
        card["name"] = card["name"].split(" | ", 1)[1]
        for a in dirty["actions"]:
            if a["data"]["card"]["id"] == card["id"]:
                a["data"]["card"]["name"] = card["name"]
    load(db, world, dirty)
    report = rebuild_event_log(db)
    lost = sum(1 for a in dirty["actions"] if a["data"]["card"]["id"] in {c["id"] for c in renamed})
    assert report.skipped["kartu_tanpa_kode_task"] == lost
    assert report.cases == sum(1 for c in board["cards"] if code_of(c).startswith("TSK-")) - 2


# --- endpoint dan izin --------------------------------------------------------------------------


@pytest.fixture
def login(client, db):
    """Header untuk satu peran. Client bawaan memegang semua peran (conftest)."""

    def as_role(role: str) -> dict:
        token = make_token(db, f"uji{role}".replace("_", ""), [role])
        return {"Authorization": f"Bearer {token}"}

    return as_role


def test_endpoints_need_login(client):
    del client.headers["Authorization"]
    assert client.post(f"{URL}/rebuild").status_code == 401
    assert client.get(URL).status_code == 401


def test_roles_without_permission_get_403(client, login):
    headers = login("anggota_tim")
    assert client.post(f"{URL}/rebuild", headers=headers).status_code == 403
    assert client.get(URL, headers=headers).status_code == 403


def test_admin_data_can_rebuild_and_read(client, db, world, board, login):
    load(db, world, board)
    headers = login("admin_data")
    report = client.post(f"{URL}/rebuild", headers=headers)
    assert report.status_code == 200
    assert report.json()["cases"] > 0

    project = world.projects[0].project_id
    listed = client.get(URL, headers=headers, params={"project_id": project})
    assert listed.status_code == 200
    assert listed.json() and {e["project_id"] for e in listed.json()} == {project}
    first = listed.json()[0]
    assert set(first) >= {"case_id", "activity", "event_time", "resource_id", "actor_name"}


@pytest.mark.parametrize(
    "params",
    [{"date_from": "2026-10-02", "date_to": "2026-10-01"}, {"project_id": "PRJ-1"}],
)
def test_invalid_filters_are_422(client, login, params):
    assert client.get(URL, headers=login("admin_data"), params=params).status_code == 422
