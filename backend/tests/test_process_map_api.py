"""DIG-169: GET /digital-twin/process-map dari event log data sintetis seed 42.

Angka acuan diambil dari laporan event log awal DIG-167 (EVENT_LOG_AWAL_ITERASI1.md, dibuat
skrip discovery terpisah dari service ini), lalu seluruh DFG dibandingkan dengan hitungan
independen dari GET /data/event-log.
"""

import statistics
from collections import Counter, defaultdict
from datetime import date

import pytest

from app.modules.data.event_log import WIB, list_event_log, rebuild_event_log
from synthetic.raw_sources import trello_board
from synthetic.world import build_world
from tests.conftest import REQUIRES_DB, make_token
from tests.test_event_log_build import AS_OF, load

pytestmark = REQUIRES_DB

URL = "/api/v1/digital-twin/process-map"
FLOW_KINDS = {"created", "status", "archived", "deleted"}


@pytest.fixture(scope="module")
def world():
    return build_world(42, AS_OF)


@pytest.fixture(scope="module")
def board(world):
    return trello_board(world)


@pytest.fixture
def loaded(client, db, world, board):
    load(db, world, board)
    rebuild_event_log(db)


def get(client, **params):
    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def edges_of(body) -> dict[tuple[str, str], dict]:
    return {(e["source"], e["target"]): e for e in body["edges"]}


def independent_dfg(db, kinds, **filters):
    """Sama dengan dfg() di discovery_event_log_awal.py: pasangan berurutan per case."""
    cases = defaultdict(list)
    for e in list_event_log(db, **filters):
        if e.activity_kind in kinds:
            cases[e.case_id].append(e)
    gaps = defaultdict(list)
    for events in cases.values():
        for a, b in zip(events, events[1:]):
            gaps[(a.activity, b.activity)].append(
                (b.event_time - a.event_time).total_seconds() / 3600
            )
    return cases, gaps


# --- cocok dengan laporan DIG-167 dan hitungan independen ------------------------------------


def test_default_map_matches_initial_event_log_report(loaded, client):
    body = get(client)
    assert body["activity_kinds"] == ["created", "status", "archived", "deleted"]
    assert body["cases"] == 136
    assert len(body["edges"]) == 8
    edges = edges_of(body)
    first = edges[("Task dibuat", "To Do")]
    assert (first["frequency"], round(first["mean_hours"], 1), round(first["median_hours"], 1)) == (
        85,
        4.1,
        4.0,
    )
    assert edges[("To Do", "In Progress")]["frequency"] == 75
    assert edges[("In Progress", "Done")]["frequency"] == 61
    assert body["start_activities"] == [{"activity": "Task dibuat", "cases": 136}]
    ends = {a["activity"]: a["cases"] for a in body["end_activities"]}
    assert (ends["Done"], ends["Task dibuat"]) == (61, 50)
    assert body["max_edge_frequency"] == 85
    assert body["hidden"] == {"edges": 0, "nodes": 0, "edge_frequency": 0}


def test_every_edge_matches_an_independent_count(loaded, client, db):
    body = get(client)
    cases, gaps = independent_dfg(db, FLOW_KINDS)
    assert set(edges_of(body)) == set(gaps)
    for key, edge in edges_of(body).items():
        assert edge["frequency"] == len(gaps[key]), key
        assert edge["mean_hours"] == round(statistics.fmean(gaps[key]), 2), key
        assert edge["median_hours"] == round(statistics.median(gaps[key]), 2), key
    nodes = {n["id"]: n for n in body["nodes"]}
    counted = Counter(e.activity for events in cases.values() for e in events)
    assert {k: n["frequency"] for k, n in nodes.items()} == dict(counted)
    assert body["events"] == sum(counted.values())
    assert sum(n["start_cases"] for n in body["nodes"]) == body["cases"]
    assert sum(n["end_cases"] for n in body["nodes"]) == body["cases"]


def test_nodes_and_edges_are_sorted_by_frequency(loaded, client):
    body = get(client)
    assert [n["frequency"] for n in body["nodes"]] == sorted(
        (n["frequency"] for n in body["nodes"]), reverse=True
    )
    assert [e["frequency"] for e in body["edges"]] == sorted(
        (e["frequency"] for e in body["edges"]), reverse=True
    )
    assert all(n["id"] == n["label"] for n in body["nodes"])


def test_assignment_and_change_events_can_be_included(loaded, client):
    body = get(client, activity_kinds=["created", "status", "assignment", "change_event"])
    edges = edges_of(body)
    assert edges[("Task dibuat", "Anggota ditugaskan")]["frequency"] == 85
    assert edges[("In Progress", "Overrun dicatat")]["frequency"] == 4
    assert body["activity_kinds"] == ["created", "status", "assignment", "change_event"]


# --- filter -----------------------------------------------------------------------------------


def test_min_frequency_hides_rare_paths_and_reports_them(loaded, client):
    full = get(client)
    body = get(client, min_frequency=5)
    rare = [e for e in full["edges"] if e["frequency"] < 5]
    assert all(e["frequency"] >= 5 for e in body["edges"])
    assert body["hidden"]["edges"] == len(rare)
    assert body["hidden"]["edge_frequency"] == sum(e["frequency"] for e in rare)
    assert body["hidden"]["nodes"] == len(full["nodes"]) - len(body["nodes"])
    assert body["max_edge_frequency"] == full["max_edge_frequency"] == 85
    shown = {n["id"] for n in body["nodes"]}
    assert all({e["source"], e["target"]} <= shown for e in body["edges"])


def test_project_filter(loaded, client, db, world):
    project = world.projects[0].project_id
    body = get(client, project_id=project)
    cases, gaps = independent_dfg(db, FLOW_KINDS, project_id=project)
    assert body["project_id"] == project
    assert body["cases"] == len(cases)
    assert {k: e["frequency"] for k, e in edges_of(body).items()} == {
        k: len(v) for k, v in gaps.items()
    }


def test_date_range_cuts_traces(loaded, client, db):
    day = date(2026, 9, 1)
    body = get(client, date_from="2026-09-01", date_to="2026-09-30")
    cases, _ = independent_dfg(db, FLOW_KINDS, date_from=day, date_to=date(2026, 9, 30))
    assert body["cases"] == len(cases) > 0
    assert body["events"] == sum(len(v) for v in cases.values())
    assert all(
        day <= e.event_time.astimezone(WIB).date() <= date(2026, 9, 30)
        for events in cases.values()
        for e in events
    )


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "2026-10-02", "date_to": "2026-10-01"},
        {"project_id": "PRJ-1"},
        {"min_frequency": 0},
        {"activity_kinds": ["commit"]},
    ],
)
def test_invalid_query_is_422(client, params):
    assert client.get(URL, params=params).status_code == 422


# --- event log kosong ---------------------------------------------------------------------


def test_empty_event_log_is_not_an_error(client, db, world, board):
    load(db, world, board)  # sumber ada, tetapi event log belum dibangun ulang
    body = get(client)
    assert (body["event_log_events"], body["cases"], body["nodes"], body["edges"]) == (0, 0, [], [])
    assert body["max_edge_frequency"] == 0


def test_filter_without_match_keeps_total_events(loaded, client):
    body = get(client, date_from="2030-01-01")
    assert body["event_log_events"] > 0
    assert (body["cases"], body["nodes"]) == (0, [])


# --- izin (FR-08) --------------------------------------------------------------------------


def test_requires_login(client):
    del client.headers["Authorization"]
    assert client.get(URL).status_code == 401


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("kaur_asman", True),
        ("system_analyst", True),
        ("anggota_tim", False),
        ("admin_data", False),
        ("admin_it", False),
    ],
)
def test_permission_per_role(client, db, role, allowed):
    token = make_token(db, f"uji{role}".replace("_", ""), [role])
    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == (200 if allowed else 403)
