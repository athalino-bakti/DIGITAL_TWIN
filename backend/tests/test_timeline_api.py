"""DIG-177: endpoint /api/v1/digital-twin/timeline terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest

from app.modules.data.models import Assignment, ChangeEvent, Task
from tests.conftest import REQUIRES_DB, make_token

pytestmark = REQUIRES_DB

URL = "/api/v1/digital-twin/timeline"
DATA = "/api/v1/data"


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


def member(client, name) -> str:
    response = client.post(
        f"{DATA}/resources",
        json={
            "resource_name": name,
            "primary_role_id": "ROLE-BE",
            "secondary_role_ids": [],
            "cross_role_capable": False,
            "join_date": "2024-01-01",
            "seniority": "mid",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource_id"]


def task(db, task_id, project_id, phase, start, finish, **extra):
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
            phase=phase,
            planned_start=start,
            planned_finish=finish,
            **extra,
        )
    )


@pytest.fixture
def data(client, db) -> dict:
    simak, sikep = project(client, "SIMAK", 2), project(client, "SIKEP", 1)
    kosong = project(client, "Kosong", 3)
    sari, budi = member(client, "Sari"), member(client, "Budi")
    task(
        db,
        "TSK-0001",
        sikep,
        "be_dev",
        date(2026, 3, 2),
        date(2026, 3, 6),
        status="done",
        actual_start=date(2026, 3, 2),
        actual_finish=date(2026, 3, 10),
    )  # terlambat 2 hari kerja
    task(
        db,
        "TSK-0002",
        sikep,
        "planning",
        date(2026, 2, 2),
        date(2026, 2, 6),
        status="done",
        actual_start=date(2026, 2, 2),
        actual_finish=date(2026, 2, 5),
    )
    task(
        db,
        "TSK-0003",
        sikep,
        "be_dev",
        date(2026, 3, 9),
        date(2026, 3, 13),
        status="in_progress",
        actual_start=date(2026, 3, 9),
    )
    task(db, "TSK-0004", simak, "fe_dev", date(2026, 3, 2), date(2026, 3, 6), status="dropped")
    db.flush()
    db.add_all(
        [
            Assignment(
                assignment_id="ASG-0001",
                task_id="TSK-0001",
                resource_id=sari,
                role_in_task="ROLE-BE",
                assigned_date=date(2026, 3, 2),
                released_date=date(2026, 3, 4),
            ),
            Assignment(
                assignment_id="ASG-0002",
                task_id="TSK-0001",
                resource_id=budi,
                role_in_task="ROLE-BE",
                assigned_date=date(2026, 3, 4),
                is_takeover=True,
            ),
            Assignment(
                assignment_id="ASG-0003",
                task_id="TSK-0003",
                resource_id=sari,
                role_in_task="ROLE-BE",
                assigned_date=date(2026, 3, 9),
            ),
            ChangeEvent(
                event_id="EVT-001",
                project_id=sikep,
                event_type="blocker",
                event_date=date(2026, 3, 5),
                affected_task_id="TSK-0001",
            ),
            ChangeEvent(
                event_id="EVT-002",
                project_id=simak,
                event_type="hotfix",
                event_date=date(2026, 3, 3),
            ),
        ]
    )
    db.commit()
    client.post(f"{DATA}/holidays", json={"holiday_date": "2026-03-09", "holiday_name": "Libur"})
    client.post(f"{DATA}/holidays", json={"holiday_date": "2026-12-25", "holiday_name": "Natal"})
    return {"sikep": sikep, "simak": simak, "kosong": kosong, "sari": sari, "budi": budi}


def get(client, **params) -> dict:
    response = client.get(URL, params={"as_of": "2026-03-20"} | params)
    assert response.status_code == 200, response.text
    return response.json()


def test_grouped_by_project_priority_then_phase(client, data):
    body = get(client)
    assert [p["project_name"] for p in body["projects"]] == ["SIKEP", "SIMAK"]  # tanpa "Kosong"
    sikep = body["projects"][0]
    assert [ph["phase"] for ph in sikep["phases"]] == ["planning", "be_dev"]
    assert [t["task_id"] for t in sikep["phases"][1]["tasks"]] == ["TSK-0001", "TSK-0003"]
    assert (sikep["task_count"], sikep["late_count"]) == (3, 2)
    assert (body["range_start"], body["range_end"]) == ("2026-02-02", "2026-03-13")


def test_delay_fields_and_assignees(client, data):
    tasks = {
        t["task_id"]: t for p in get(client)["projects"] for ph in p["phases"] for t in ph["tasks"]
    }
    late = tasks["TSK-0001"]
    # Selesai 10 Maret, libur 9 Maret: 4 hari kalender, 1 hari kerja.
    assert (late["is_late"], late["delay_days"], late["delay_working_days"]) == (True, 4, 1)
    assert late["assignees"] == ["Budi"]  # Sari sudah dilepas
    assert tasks["TSK-0002"]["is_late"] is False
    assert (tasks["TSK-0003"]["is_late"], tasks["TSK-0003"]["delay_days"]) == (True, 7)
    assert tasks["TSK-0004"]["is_late"] is False  # dropped


def test_as_of_changes_open_tasks_only(client, data):
    sikep = get(client, as_of="2026-03-13")["projects"][0]
    assert sikep["late_count"] == 1


def test_events_and_holidays_within_range(client, data):
    body = get(client)
    assert [(e["event_id"], e["event_type"]) for e in body["events"]] == [
        ("EVT-002", "hotfix"),
        ("EVT-001", "blocker"),
    ]
    assert [h["holiday_date"] for h in body["holidays"]] == ["2026-03-09"]


def test_filter_by_project(client, data):
    body = get(client, project_id=data["simak"])
    assert [p["project_name"] for p in body["projects"]] == ["SIMAK"]
    assert [e["event_id"] for e in body["events"]] == ["EVT-002"]
    empty = get(client, project_id=data["kosong"])
    assert empty["projects"][0]["task_count"] == 0
    assert (empty["range_start"], empty["holidays"]) == (None, [])


def test_filter_by_member_includes_released_assignments(client, data):
    body = get(client, resource_id=data["sari"])
    ids = [t["task_id"] for p in body["projects"] for ph in p["phases"] for t in ph["tasks"]]
    assert ids == ["TSK-0001", "TSK-0003"]
    assert [e["event_id"] for e in body["events"]] == ["EVT-001"]
    assert get(client, resource_id=data["budi"])["projects"][0]["task_count"] == 1


def test_empty_database_and_bad_params(client):
    body = get(client)
    assert (body["projects"], body["events"], body["range_start"]) == ([], [], None)
    assert client.get(URL, params={"project_id": "bukan-id"}).status_code == 422
    assert client.get(URL, params={"as_of": "20-03-2026"}).status_code == 422


@pytest.mark.parametrize(
    "role,status",
    [
        (None, 401),
        ("admin_data", 403),
        ("anggota_tim", 403),
        ("kaur_asman", 200),
        ("system_analyst", 200),
    ],
)
def test_needs_baseline_read(client, db, role, status):
    token = make_token(db, f"uji_{role}", [role]) if role else ""
    headers = {"Authorization": f"Bearer {token}" if role else ""}
    assert client.get(URL, headers=headers).status_code == status
