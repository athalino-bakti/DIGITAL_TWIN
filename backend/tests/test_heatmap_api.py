"""DIG-188: GET /api/v1/digital-twin/workload-heatmap terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest
from sqlalchemy import update

from app.modules.auth.models import AppUser
from app.modules.data.models import Assignment, Availability, Holiday, Task, WorkloadItem
from tests.conftest import REQUIRES_DB, make_token

pytestmark = REQUIRES_DB

URL = "/api/v1/digital-twin/workload-heatmap"
DATA = "/api/v1/data"
PARAMS = {"start": "2026-03-04", "weeks": 2, "as_of": "2026-03-04"}  # Rabu, dibulatkan ke Senin


def project(client, name, priority) -> str:
    response = client.post(
        f"{DATA}/projects",
        json={
            "project_name": name,
            "process_owner": "Urusan Kepegawaian",
            "priority_rank": priority,
            "start_date": "2026-01-05",
            "target_launch_date": "2026-06-30",
            "status": "development",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def member(client, name, role="ROLE-BE", join="2024-01-01") -> str:
    response = client.post(
        f"{DATA}/resources",
        json={
            "resource_name": name,
            "primary_role_id": role,
            "secondary_role_ids": [],
            "cross_role_capable": False,
            "join_date": join,
            "seniority": "mid",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource_id"]


def task(task_id, project_id, complexity, status="in_progress") -> Task:
    return Task(
        task_id=task_id,
        project_id=project_id,
        feature_name="Cuti",
        task_name=f"Task {task_id}",
        required_role_id="ROLE-BE",
        complexity_id=complexity,
        priority_rank=1,
        estimated_days=5.0,
        phase="be_dev",
        planned_start=date(2026, 3, 2),
        planned_finish=date(2026, 3, 13),
        actual_start=date(2026, 3, 2),
        status=status,
    )


def assign(number, task_id, resource_id) -> Assignment:
    return Assignment(
        assignment_id=f"ASG-{number:04d}",
        task_id=task_id,
        resource_id=resource_id,
        role_in_task="ROLE-BE",
        assigned_date=date(2026, 3, 2),
    )


@pytest.fixture
def team(client, db) -> dict:
    sikep, simak = project(client, "SIKEP", 1), project(client, "SIMAK", 2)
    sari = member(client, "Sari")
    budi = member(client, "Budi", role="ROLE-FE")
    nina = member(client, "Nina", join="2026-02-20")  # onboarding: faktor 0,50
    member(client, "Oki", join="2026-04-01")  # belum bergabung di rentang: tidak muncul
    db.add_all(
        [
            task("TSK-0001", sikep, "CX-H"),
            task("TSK-0002", simak, "CX-M"),
            task("TSK-0003", simak, "CX-M", status="on_hold"),
        ]
    )
    db.flush()
    db.add_all(
        [
            assign(1, "TSK-0001", sari),
            assign(2, "TSK-0002", sari),
            assign(3, "TSK-0003", budi),
            assign(4, "TSK-0001", nina),
            assign(5, "TSK-0002", nina),
            WorkloadItem(
                item_id="WLI-0001",
                resource_id=sari,
                item_type="ticket",
                severity="high",
                received_date=date(2026, 3, 2),
                started_date=date(2026, 3, 2),
                resolved_date=date(2026, 3, 3),
            ),
            Availability(
                availability_id="AVL-001",
                resource_id=sari,
                date_start=date(2026, 3, 6),
                date_end=date(2026, 3, 6),
                absence_type="planned_leave",
            ),
            Holiday(holiday_date=date(2026, 3, 9), holiday_name="Libur sintetis"),
        ]
    )
    db.commit()
    return {"sikep": sikep, "simak": simak, "sari": sari, "budi": budi, "nina": nina}


def fetch(client, headers=None, **params) -> dict:
    response = client.get(URL, params={**PARAMS, **params}, headers=headers or {})
    assert response.status_code == 200, response.text
    return response.json()


def rows(body) -> dict:
    return {row["resource_id"]: row for row in body["rows"]}


def test_heatmap_computes_rli_per_member_per_week(client, team):
    body = fetch(client)
    assert (body["formula_version"], body["provisional"]) == ("provisional-2026-11", True)
    assert [w["week_start"] for w in body["weeks"]] == ["2026-03-02", "2026-03-09"]
    assert [(w["working_days"], w["holidays"]) for w in body["weeks"]] == [
        (5, []),
        (4, ["2026-03-09"]),
    ]
    assert [c["code"] for c in body["categories"]] == [
        "rendah",
        "sedang",
        "penuh",
        "overload",
        "overload_berat",
        "tidak_tersedia",
    ]
    by_id = rows(body)
    assert list(by_id) == sorted([team["sari"], team["budi"], team["nina"]])

    first, second = by_id[team["sari"]]["cells"]
    # Contoh usulan formula: CX-H + CX-M, tiket high 2 hari, cuti 1 hari.
    assert (first["project_load"], first["non_project_load"], first["capacity"]) == (2.1, 0.24, 2.4)
    assert (first["rli"], first["category"], first["tasks"], first["workload_items"]) == (
        0.975,
        "penuh",
        2,
        1,
    )
    assert (second["rli"], second["category"], second["available_days"]) == (0.7, "sedang", 4)

    nina = by_id[team["nina"]]
    assert nina["is_onboarding"] is True
    assert (nina["cells"][0]["onboarding_factor"], nina["cells"][0]["rli"]) == (0.5, 1.4)
    assert nina["cells"][0]["category"] == "overload_berat"
    # Task on_hold tidak menambah beban.
    assert by_id[team["budi"]]["cells"][0]["rli"] == 0.0
    assert body["summary"] == {"week_start": "2026-03-02", "overloaded": 1, "resources": 3}


def test_heatmap_filters(client, team):
    assert list(rows(fetch(client, role_id="ROLE-FE"))) == [team["budi"]]
    assert list(rows(fetch(client, resource_id=team["sari"]))) == [team["sari"]]
    # Filter proyek memilih anggota, beban tetap dari semua proyek.
    by_project = rows(fetch(client, project_id=team["sikep"]))
    assert set(by_project) == {team["sari"], team["nina"]}
    assert by_project[team["sari"]]["cells"][0]["rli"] == 0.975


def test_heatmap_defaults_and_validation(client, team):
    response = client.get(URL)
    assert response.status_code == 200, response.text
    assert len(response.json()["weeks"]) == 12
    assert client.get(URL, params={"weeks": 27}).status_code == 422
    assert client.get(URL, params={"weeks": 0}).status_code == 422
    assert client.get(URL, params={"role_id": "BE"}).status_code == 422


def login_as(db, username: str, roles: list[str], resource_id: str | None = None) -> dict:
    token = make_token(db, username, roles)
    db.execute(update(AppUser).where(AppUser.username == username).values(resource_id=resource_id))
    db.commit()
    return {"Authorization": f"Bearer {token}"}


def test_member_sees_only_own_row(client, db, team):
    headers = login_as(db, "budi", ["anggota_tim"], team["budi"])
    body = fetch(client, headers, resource_id=team["sari"], role_id="ROLE-BE")
    assert list(rows(body)) == [team["budi"]]


def test_member_without_linked_resource_gets_no_rows(client, db, team):
    body = fetch(client, login_as(db, "tamu", ["anggota_tim"]))
    assert body["rows"] == []
    assert len(body["weeks"]) == 2
    assert body["weeks"][1]["holidays"] == ["2026-03-09"]


def test_read_all_roles_see_everyone(client, db, team):
    for role in ("kaur_asman", "system_analyst"):
        body = fetch(client, login_as(db, f"uji_{role}", [role]))
        assert len(body["rows"]) == 3


@pytest.mark.parametrize("role", ["admin_data", "admin_it"])
def test_roles_without_workload_permission_are_forbidden(client, db, team, role):
    response = client.get(URL, params=PARAMS, headers=login_as(db, f"uji_{role}", [role]))
    assert response.status_code == 403


def test_heatmap_needs_login(client):
    assert client.get(URL, headers={"Authorization": ""}).status_code == 401
