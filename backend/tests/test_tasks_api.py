"""DIG-161: endpoint /api/v1/data/tasks terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest

from app.modules.data.models import Task
from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

BASE = "/api/v1/data/tasks"


def project(client, name, priority) -> str:
    response = client.post(
        "/api/v1/data/projects",
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


def task(db, task_id, project_id, priority=1, role="ROLE-BE", **extra):
    db.add(
        Task(
            task_id=task_id,
            project_id=project_id,
            feature_name="Cuti",
            task_name=f"Task {task_id}",
            required_role_id=role,
            complexity_id="CX-M",
            priority_rank=priority,
            estimated_days=3.0,
            phase="be_dev",
            planned_start=date(2026, 3, 2),
            planned_finish=date(2026, 3, 5),
            **extra,
        )
    )
    db.commit()


@pytest.fixture
def tasks(client, db) -> dict:
    sikep, simak = project(client, "SIKEP", 1), project(client, "SIMAK", 2)
    task(db, "TSK-0001", sikep, priority=2)
    task(db, "TSK-0002", sikep, priority=1, role="ROLE-FE")
    task(
        db,
        "TSK-0003",
        simak,
        status="in_progress",
        actual_start=date(2026, 3, 3),
    )
    return {"sikep": sikep, "simak": simak}


def test_list_order_and_filters(client, tasks):
    rows = client.get(BASE).json()
    assert [r["task_id"] for r in rows] == ["TSK-0002", "TSK-0001", "TSK-0003"]
    assert rows[0]["project_name"] == "SIKEP" and rows[0]["status"] == "not_started"
    assert len(client.get(BASE, params={"project_id": tasks["simak"]}).json()) == 1
    assert len(client.get(BASE, params=[("status", "in_progress"), ("status", "done")]).json()) == 1
    assert [
        r["task_id"] for r in client.get(BASE, params={"required_role_id": "ROLE-FE"}).json()
    ] == ["TSK-0002"]
    assert client.get(BASE, params={"status": "selesai"}).status_code == 422


def test_get_one(client, tasks):
    assert client.get(f"{BASE}/TSK-0003").json()["actual_start"] == "2026-03-03"
    assert client.get(f"{BASE}/TSK-9999").status_code == 404


def patch(client, task_id, **body):
    return client.patch(f"{BASE}/{task_id}/status", json=body)


def test_task_lifecycle(client, tasks):
    response = patch(client, "TSK-0001", status="in_progress", actual_start="2026-03-02")
    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["actual_start"]) == (
        "in_progress",
        "2026-03-02",
    )
    assert patch(client, "TSK-0001", status="in_qa").status_code == 200
    response = patch(
        client, "TSK-0001", status="done", actual_finish="2026-03-06", dod_fulfilled=True
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["actual_finish"], body["dod_fulfilled"]) == (
        "done",
        "2026-03-06",
        True,
    )


@pytest.mark.parametrize(
    "task_id,body,expected",
    [
        ("TSK-0001", {"status": "in_progress"}, ["actual_start"]),
        ("TSK-0003", {"status": "done"}, ["actual_finish"]),
        ("TSK-0003", {"actual_finish": "2026-03-04"}, ["actual_finish"]),
        ("TSK-0003", {"status": "done", "actual_finish": "2026-03-01"}, ["actual_finish"]),
        ("TSK-0003", {"dod_fulfilled": True}, ["dod_fulfilled"]),
        ("TSK-0003", {"status": "not_started"}, ["actual_start"]),
        ("TSK-0003", {"status": None}, ["status"]),
    ],
)
def test_rules_on_merged_values(client, tasks, task_id, body, expected):
    response = patch(client, task_id, **body)
    assert response.status_code == 422, response.text
    assert error_fields(response) == expected


def test_back_to_not_started_by_clearing_start(client, tasks):
    response = patch(client, "TSK-0003", status="not_started", actual_start=None)
    assert response.status_code == 200, response.text
    assert response.json()["actual_start"] is None


def test_only_status_columns_can_be_changed(client, tasks):
    response = patch(client, "TSK-0001", priority_rank=5)
    assert response.status_code == 422
    assert error_fields(response) == ["priority_rank"]
    assert patch(client, "TSK-9999", status="done").status_code == 404
    assert patch(client, "TSK-0001", actual_start="02/03/2026").status_code == 422
