"""DIG-175: GET /api/v1/digital-twin/summary terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest

from app.modules.data.models import Assignment, Task
from tests.conftest import REQUIRES_DB, make_token

pytestmark = REQUIRES_DB

URL = "/api/v1/digital-twin/summary"
DATA = "/api/v1/data"
AS_OF = "2026-03-16"


def project(client, name, priority, status="development", target="2026-03-31") -> str:
    response = client.post(
        f"{DATA}/projects",
        json={
            "project_name": name,
            "process_owner": "Urusan Kepegawaian",
            "priority_rank": priority,
            "start_date": "2026-01-05",
            "target_launch_date": target,
            "status": status,
            **({"actual_launch_date": target} if status == "released" else {}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def member(client, name, secondary=()) -> str:
    response = client.post(
        f"{DATA}/resources",
        json={
            "resource_name": name,
            "primary_role_id": "ROLE-BE",
            "secondary_role_ids": list(secondary),
            "cross_role_capable": False,
            "join_date": "2024-01-01",
            "seniority": "mid",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource_id"]


def task(db, task_id, project_id, finish, status="in_progress", actual=None):
    started = status in ("in_progress", "in_qa", "blocked", "done")
    db.add(
        Task(
            task_id=task_id,
            project_id=project_id,
            feature_name="Cuti",
            task_name=f"Task {task_id}",
            required_role_id="ROLE-BE",
            complexity_id="CX-M",
            priority_rank=1,
            estimated_days=3.0,
            phase="be_dev",
            planned_start=date(2026, 3, 2),
            planned_finish=finish,
            actual_start=date(2026, 3, 2) if started else None,
            actual_finish=actual,
            status=status,
        )
    )
    db.commit()


def assign(db, assignment_id, task_id, resource_id, role, released=None):
    db.add(
        Assignment(
            assignment_id=assignment_id,
            task_id=task_id,
            resource_id=resource_id,
            role_in_task=role,
            assigned_date=date(2026, 3, 2),
            released_date=released,
        )
    )
    db.commit()


@pytest.fixture
def data(client, db) -> dict:
    sikep = project(client, "SIKEP", 1, target="2026-03-13")  # task lewat rencana
    simak = project(client, "SIMAK", 2)  # sesuai jadwal
    sipeg = project(client, "SIPEG", 3, status="testing", target="2026-03-10")  # selesai telat
    project(client, "Arsip", 4, status="on_hold")
    project(client, "Portal", 5, status="released", target="2026-02-27")
    task(db, "TSK-0001", sikep, date(2026, 3, 6))  # lewat rencana
    task(db, "TSK-0002", sikep, date(2026, 3, 20), status="not_started")
    task(db, "TSK-0003", simak, date(2026, 3, 27))
    task(db, "TSK-0004", simak, date(2026, 4, 30), status="dropped")  # tidak dihitung
    task(db, "TSK-0005", sipeg, date(2026, 3, 9), status="done", actual=date(2026, 3, 12))
    sari = member(client, "Sari", secondary=["ROLE-QA"])  # peran rangkap
    budi = member(client, "Budi")  # sedang mengerjakan peran lain
    dewi = member(client, "Dewi")  # peran lain, tetapi task sudah selesai
    eko = member(client, "Eko")  # peran lain, tetapi penugasan sudah dilepas
    member(client, "Fajar")  # hanya peran utama
    assign(db, "ASG-0001", "TSK-0003", budi, "ROLE-FE")
    assign(db, "ASG-0002", "TSK-0005", dewi, "ROLE-FE")
    assign(db, "ASG-0003", "TSK-0001", eko, "ROLE-FE", released=date(2026, 3, 10))
    assign(db, "ASG-0004", "TSK-0001", sari, "ROLE-BE")
    return {"sikep": sikep, "simak": simak, "sipeg": sipeg, "sari": sari, "budi": budi}


def fetch(client) -> dict:
    response = client.get(URL, params={"as_of": AS_OF})
    assert response.status_code == 200, response.text
    return response.json()


def test_active_projects_are_planning_development_testing(client, data):
    card = fetch(client)["active_projects"]
    assert card["count"] == 3
    assert [p["project_name"] for p in card["items"]] == ["SIKEP", "SIMAK", "SIPEG"]


def test_late_projects_use_projection(client, data):
    body = fetch(client)
    card = body["late_projects"]
    assert body["as_of"] == AS_OF
    # Urut dari yang paling telat. SIMAK (proyeksi 27 Maret, target 31 Maret) tidak telat,
    # dan task dropped 30 April-nya tidak dihitung.
    assert [p["project_name"] for p in card["items"]] == ["SIKEP", "SIPEG"]
    assert card["count"] == 2
    sikep, sipeg = card["items"]
    # TSK-0002 rencana 20 Maret; TSK-0001 lewat rencana sehingga paling cepat 16 Maret.
    assert (sikep["projected_finish"], sikep["days_late"]) == ("2026-03-20", 7)
    assert (sikep["open_tasks"], sikep["late_open_tasks"]) == (2, 1)
    # SIPEG selesai 12 Maret, target 10 Maret.
    assert (sipeg["projected_finish"], sipeg["days_late"]) == ("2026-03-12", 2)
    assert (sipeg["open_tasks"], sipeg["late_open_tasks"]) == (0, 0)


def test_project_past_target_by_open_late_task(client, db, data):
    # Task SIMAK lewat rencana dan belum selesai pada 2 April: proyeksi jadi 2 April > 31 Maret.
    response = client.get(URL, params={"as_of": "2026-04-02"})
    names = [p["project_name"] for p in response.json()["late_projects"]["items"]]
    assert "SIMAK" in names


def test_overload_card_is_pending_rli(client, data):
    card = fetch(client)["overloaded_resources"]
    assert card["count"] is None
    assert "DIG-187" in card["reason"]


def test_multi_role_resources(client, data):
    card = fetch(client)["multi_role_resources"]
    by_name = {r["resource_name"]: r for r in card["items"]}
    assert set(by_name) == {"Sari", "Budi"}
    assert by_name["Sari"]["secondary_role_ids"] == ["ROLE-QA"]
    assert by_name["Sari"]["other_active_roles"] == []
    assert by_name["Budi"]["other_active_roles"] == ["ROLE-FE"]
    assert card["count"] == 2


def test_empty_database(client):
    body = fetch(client)
    assert body["active_projects"] == {"count": 0, "items": []}
    assert body["late_projects"] == {"count": 0, "items": []}
    assert body["multi_role_resources"] == {"count": 0, "items": []}


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("kaur_asman", 200),
        ("system_analyst", 200),
        ("anggota_tim", 403),
        ("admin_data", 403),
        ("admin_it", 403),
    ],
)
def test_permission_per_role(client, db, role, expected):
    headers = {"Authorization": f"Bearer {make_token(db, f'uji_{role}', [role])}"}
    assert client.get(URL, headers=headers).status_code == expected
