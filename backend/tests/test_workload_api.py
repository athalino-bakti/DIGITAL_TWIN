"""DIG-136 dan DIG-138: endpoint /api/v1/data/workload-items terhadap PostgreSQL sungguhan."""

import pytest
from sqlalchemy import text

from app.modules.data.workload_service import CSV_COLUMNS
from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

BASE = "/api/v1/data/workload-items"
IMPORT = f"{BASE}/import"
HEADER = ",".join(CSV_COLUMNS)


@pytest.fixture
def team(client) -> dict:
    """Dua anggota, satu aplikasi yang sudah rilis 1 Sep 2026, dan satu yang masih development."""
    ids = {}
    for key, name in (("sari", "Sari P."), ("budi", "Budi")):
        response = client.post(
            "/api/v1/data/resources",
            json={
                "resource_name": name,
                "primary_role_id": "ROLE-BE",
                "join_date": "2024-02-01",
                "seniority": "mid",
            },
        )
        assert response.status_code == 201, response.text
        ids[key] = response.json()["resource_id"]
    base = {
        "process_owner": "Urusan Kepegawaian",
        "start_date": "2026-03-02",
        "target_launch_date": "2026-08-28",
    }
    for key, extra in (
        (
            "released",
            {
                "project_name": "Sistem Cuti",
                "priority_rank": 3,
                "status": "released",
                "actual_launch_date": "2026-09-01",
            },
        ),
        ("dev", {"project_name": "Sistem Presensi", "priority_rank": 1, "status": "development"}),
    ):
        response = client.post("/api/v1/data/projects", json=base | extra)
        assert response.status_code == 201, response.text
        ids[key] = response.json()["project_id"]
    return ids


def body(team: dict, **overrides) -> dict:
    return {
        "resource_id": team["sari"],
        "item_type": "ticket",
        "received_date": "2026-10-05",
        "severity": "medium",
    } | overrides


def create(client, team, **overrides) -> dict:
    response = client.post(BASE, json=body(team, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --- CRUD (DIG-136) ---


def test_create_assigns_four_digit_id_and_reads_back(client, team):
    item = create(client, team, related_project_id=team["released"])
    assert item == {
        "item_id": "WLI-0001",
        "resource_id": team["sari"],
        "resource_name": "Sari P.",
        "item_type": "ticket",
        "related_project_id": team["released"],
        "project_name": "Sistem Cuti",
        "received_date": "2026-10-05",
        "started_date": None,
        "resolved_date": None,
        "severity": "medium",
        "is_hotfix": False,
        "status": "waiting",
    }
    assert create(client, team)["item_id"] == "WLI-0002"


def test_explicit_and_duplicate_id(client, team):
    create(client, team, item_id="WLI-0041")
    assert create(client, team)["item_id"] == "WLI-0042"
    response = client.post(BASE, json=body(team, item_id="WLI-0041"))
    assert response.status_code == 409
    assert error_fields(response) == ["item_id"]


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"resource_id": "RES-999"}, "resource_id"),
        ({"related_project_id": "PRJ-999"}, "related_project_id"),
        ({"started_date": "2026-10-04"}, "started_date"),
        ({"resolved_date": "2026-10-04"}, "resolved_date"),
        ({"started_date": "2026-10-07", "resolved_date": "2026-10-06"}, "resolved_date"),
        ({"received_date": "05/10/2026"}, "received_date"),
        ({"item_type": "tiket"}, "item_type"),
        ({"severity": "urgent"}, "severity"),
        ({"is_hotfix": "ya"}, "is_hotfix"),
        ({"item_id": "WLI-1"}, "item_id"),
    ],
)
def test_invalid_values_are_422(client, team, overrides, field):
    response = client.post(BASE, json=body(team, **overrides))
    assert response.status_code == 422
    assert error_fields(response) == [field]


def test_status_follows_dates(client, team):
    waiting = create(client, team)
    started = create(client, team, started_date="2026-10-06")
    resolved = create(client, team, started_date="2026-10-06", resolved_date="2026-10-08")
    assert [waiting["status"], started["status"], resolved["status"]] == [
        "waiting",
        "in_progress",
        "resolved",
    ]


def test_list_filters_and_order(client, team):
    old = create(client, team, received_date="2026-09-10", resolved_date="2026-09-11")
    new = create(client, team, resource_id=team["budi"], item_type="operational")
    linked = create(client, team, received_date="2026-10-01", related_project_id=team["dev"])

    def ids(params: dict) -> list[str]:
        response = client.get(BASE, params=params)
        assert response.status_code == 200, response.text
        return [item["item_id"] for item in response.json()]

    assert ids({}) == [new["item_id"], linked["item_id"], old["item_id"]]
    assert ids({"resource_id": team["budi"]}) == [new["item_id"]]
    assert ids({"item_type": "ticket"}) == [linked["item_id"], old["item_id"]]
    assert ids({"related_project_id": team["dev"]}) == [linked["item_id"]]
    assert ids({"open_only": "true"}) == [new["item_id"], linked["item_id"]]
    assert ids({"received_from": "2026-10-01", "received_to": "2026-10-04"}) == [linked["item_id"]]


def test_patch_rechecks_rules(client, team):
    item_id = create(client, team)["item_id"]
    response = client.patch(f"{BASE}/{item_id}", json={"started_date": "2026-10-06"})
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"

    response = client.patch(f"{BASE}/{item_id}", json={"received_date": "2026-10-07"})
    assert response.status_code == 422
    assert error_fields(response) == ["started_date"]

    response = client.patch(f"{BASE}/{item_id}", json={"item_type": None})
    assert response.status_code == 422
    assert error_fields(response) == ["item_type"]

    response = client.patch(f"{BASE}/{item_id}", json={"item_id": "WLI-9999"})
    assert response.status_code == 422


def test_delete_and_missing(client, team):
    item_id = create(client, team)["item_id"]
    assert client.delete(f"{BASE}/{item_id}").status_code == 204
    assert client.delete(f"{BASE}/{item_id}").status_code == 404
    assert client.patch(f"{BASE}/WLI-9999", json={}).status_code == 404


def test_deleting_member_with_workload_is_409(client, team):
    create(client, team)
    assert client.delete(f"/api/v1/data/resources/{team['sari']}").status_code == 409


# --- hotfix (DIG-138) ---


def test_hotfix_on_released_app(client, team):
    item = create(
        client,
        team,
        is_hotfix=True,
        related_project_id=team["released"],
        severity="critical",
        started_date="2026-10-05",
    )
    assert item["is_hotfix"] is True


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"item_type": "operational", "related_project_id": "released"}, ["is_hotfix"]),
        ({}, ["related_project_id"]),
        ({"related_project_id": "dev"}, ["related_project_id"]),
        ({"related_project_id": "released", "received_date": "2026-08-31"}, ["related_project_id"]),
    ],
)
def test_hotfix_rules(client, team, overrides, expected):
    if "related_project_id" in overrides:
        overrides["related_project_id"] = team[overrides["related_project_id"]]
    response = client.post(BASE, json=body(team, is_hotfix=True, **overrides))
    assert response.status_code == 422
    assert error_fields(response) == expected


def test_patch_cannot_turn_operational_into_hotfix(client, team):
    item_id = create(client, team, item_type="operational")["item_id"]
    response = client.patch(
        f"{BASE}/{item_id}", json={"is_hotfix": True, "related_project_id": team["released"]}
    )
    assert response.status_code == 422
    assert error_fields(response) == ["is_hotfix"]


# --- impor CSV (DIG-136) ---


def csv_rows(team: dict, *rows: str) -> str:
    return "\n".join([HEADER, *(row.format(**team) for row in rows)]) + "\n"


def run_import(client, content: str, dry_run: bool) -> dict:
    response = client.post(IMPORT, json={"content": content, "dry_run": dry_run})
    assert response.status_code == 200, response.text
    return response.json()


def stored(db) -> list[tuple]:
    return [
        tuple(row)
        for row in db.execute(
            text("SELECT item_id, resource_id, severity, is_hotfix FROM workload_items ORDER BY 1")
        )
    ]


def test_import_dry_run_then_apply(client, team, db):
    content = csv_rows(
        team,
        "WLI-0010,{sari},ticket,{released},2026-10-05,2026-10-05,2026-10-06,critical,true",
        ",{budi},operational,,2026-10-07,,,low,false",
    )
    preview = run_import(client, content, dry_run=True)
    assert preview == {
        "dry_run": True,
        "applied": False,
        "total": 2,
        "inserted": 2,
        "updated": 0,
        "error_count": 0,
        "errors": [],
    }
    assert stored(db) == []

    result = run_import(client, content, dry_run=False)
    assert (result["applied"], result["inserted"], result["updated"]) == (True, 2, 0)
    assert stored(db) == [
        ("WLI-0010", team["sari"], "critical", True),
        ("WLI-0011", team["budi"], "low", False),
    ]


def test_reimport_updates_instead_of_duplicating(client, team, db):
    create(client, team, item_id="WLI-0001", severity="low")
    content = csv_rows(team, "WLI-0001,{sari},ticket,,2026-10-05,,,high,false")
    result = run_import(client, content, dry_run=False)
    assert (result["inserted"], result["updated"]) == (0, 1)
    run_import(client, content, dry_run=False)
    assert stored(db) == [("WLI-0001", team["sari"], "high", False)]


def test_import_with_any_error_saves_nothing(client, team, db):
    content = csv_rows(
        team,
        "WLI-0001,{sari},ticket,,2026-10-05,,,low,false",
        "WLI-0002,RES-999,ticket,,2026-10-05,,,low,false",
        "WLI-0003,{sari},operational,{released},2026-10-05,,,low,true",
        "WLI-0001,{budi},ticket,,2026-10-06,,,low,false",
        "WLI-0004,{sari},ticket,,2026-10-05,2026-10-01,,low,false",
    )
    result = run_import(client, content, dry_run=False)
    assert result["applied"] is False
    assert [(e["row"], e["field"]) for e in result["errors"]] == [
        (3, "resource_id"),
        (4, "is_hotfix"),
        (5, "item_id"),
        (6, "started_date"),
    ]
    assert "baris 2" in result["errors"][2]["message"]
    assert result["error_count"] == 4
    assert stored(db) == []


def test_import_wrong_header(client):
    result = run_import(client, "id,nama\nWLI-0001,x\n", dry_run=True)
    assert result["errors"][0]["row"] == 1
    assert "kolom hilang" in result["errors"][0]["message"]


def test_import_assigns_ids_after_existing(client, team, db):
    create(client, team, item_id="WLI-0099")
    content = csv_rows(
        team, ",{sari},ticket,,2026-10-05,,,low,false", ",{budi},ticket,,2026-10-05,,,low,false"
    )
    run_import(client, content, dry_run=False)
    assert [row[0] for row in stored(db)] == ["WLI-0099", "WLI-0100", "WLI-0101"]


def test_import_request_validation(client):
    assert client.post(IMPORT, json={"content": ""}).status_code == 422
    assert client.post(IMPORT, json={"content": "x", "dry_run": "ya"}).status_code == 422
