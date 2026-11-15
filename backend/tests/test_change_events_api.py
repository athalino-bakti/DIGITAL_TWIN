"""DIG-149: endpoint /api/v1/data/change-events terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest

from app.modules.data.models import Task
from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

BASE = "/api/v1/data/change-events"


def make_project(client, name: str, priority: int) -> str:
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


def make_task(db, task_id: str, project_id: str, name: str) -> None:
    db.add(
        Task(
            task_id=task_id,
            project_id=project_id,
            feature_name="Cuti",
            task_name=name,
            required_role_id="ROLE-BE",
            complexity_id="CX-M",
            priority_rank=1,
            estimated_days=3.0,
            phase="be_dev",
            planned_start=date(2026, 2, 2),
            planned_finish=date(2026, 2, 5),
        )
    )
    db.commit()


@pytest.fixture
def setup(client, db) -> dict:
    sikep = make_project(client, "SIKEP", 1)
    simak = make_project(client, "SIMAK", 2)
    make_task(db, "TSK-0001", sikep, "API pengajuan cuti")
    make_task(db, "TSK-0002", simak, "Form KRS")
    return {"sikep": sikep, "simak": simak}


def body(setup, **overrides) -> dict:
    values = {
        "project_id": setup["sikep"],
        "event_type": "change_request",
        "event_date": "2026-03-02",
        "requested_by": "Kaur",
        "decision": "accept_now",
        "resolution_mode": "extend_duration",
        "affected_task_id": "TSK-0001",
        "extension_days": 2.5,
    }
    return values | overrides


def create(client, setup, **overrides) -> dict:
    response = client.post(BASE, json=body(setup, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_assigns_id_and_returns_names(client, setup):
    event = create(client, setup)
    assert event["event_id"] == "EVT-001"
    assert event["project_name"] == "SIKEP"
    assert event["affected_task_name"] == "API pengajuan cuti"
    assert event["extension_days"] == 2.5
    assert create(client, setup)["event_id"] == "EVT-002"


def test_create_with_explicit_id_and_duplicate(client, setup):
    assert create(client, setup, event_id="EVT-0360")["event_id"] == "EVT-0360"
    response = client.post(BASE, json=body(setup, event_id="EVT-0360"))
    assert response.status_code == 409
    assert error_fields(response) == ["event_id"]


def test_blocker_with_only_required_columns(client, setup):
    event = create(
        client,
        setup,
        event_type="blocker",
        requested_by=None,
        decision=None,
        resolution_mode=None,
        affected_task_id=None,
        extension_days=None,
    )
    assert (event["decision"], event["affected_task_name"]) == (None, None)


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"project_id": "PRJ-999"}, ["project_id"]),
        ({"event_date": "2026-01-04"}, ["event_date"]),
        ({"affected_task_id": "TSK-9999"}, ["affected_task_id"]),
        ({"affected_task_id": "TSK-0002"}, ["affected_task_id"]),
        ({"extension_days": None}, ["extension_days"]),
        ({"resolution_mode": "swap_task"}, ["extension_days"]),
        ({"decision": None}, ["decision"]),
    ],
)
def test_rules(client, setup, overrides, expected):
    response = client.post(BASE, json=body(setup, **overrides))
    assert response.status_code == 422, response.text
    assert error_fields(response) == expected


@pytest.mark.parametrize(
    "overrides,field",
    [
        ({"event_type": "rapat"}, "event_type"),
        ({"decision": "maybe"}, "decision"),
        ({"event_date": "02/03/2026"}, "event_date"),
        ({"event_id": "EVT-1"}, "event_id"),
        ({"extension_days": -1}, "extension_days"),
        ({"requested_by": "x" * 101}, "requested_by"),
        ({"catatan": "kolom asing"}, "catatan"),
    ],
)
def test_body_validation(client, setup, overrides, field):
    response = client.post(BASE, json=body(setup, **overrides))
    assert response.status_code == 422
    assert field in error_fields(response)


def test_list_filters_and_order(client, setup):
    create(client, setup, event_date="2026-03-02")
    create(client, setup, event_type="priority_change", event_date="2026-04-10")
    create(
        client,
        setup,
        project_id=setup["simak"],
        affected_task_id="TSK-0002",
        event_type="blocker",
        event_date="2026-03-20",
    )
    events = client.get(BASE).json()
    assert [e["event_date"] for e in events] == ["2026-04-10", "2026-03-20", "2026-03-02"]

    per_project = client.get(BASE, params={"project_id": setup["sikep"]}).json()
    assert len(per_project) == 2
    per_task = client.get(BASE, params={"affected_task_id": "TSK-0002"}).json()
    assert [e["event_type"] for e in per_task] == ["blocker"]
    by_type = client.get(
        BASE, params=[("event_type", "change_request"), ("event_type", "priority_change")]
    ).json()
    assert len(by_type) == 2
    in_march = client.get(BASE, params={"date_from": "2026-03-01", "date_to": "2026-03-31"}).json()
    assert len(in_march) == 2


def test_get_one_and_not_found(client, setup):
    event_id = create(client, setup)["event_id"]
    assert client.get(f"{BASE}/{event_id}").json()["event_id"] == event_id
    assert client.get(f"{BASE}/EVT-999").status_code == 404
    assert client.get(f"{BASE}/bukan-id").status_code == 422


def test_patch_checks_rules_against_merged_values(client, setup):
    event_id = create(client, setup)["event_id"]
    # Ganti mode tanpa menghapus tambahan hari: ditolak.
    response = client.patch(f"{BASE}/{event_id}", json={"resolution_mode": "reshuffle"})
    assert response.status_code == 422
    assert error_fields(response) == ["extension_days"]
    response = client.patch(
        f"{BASE}/{event_id}", json={"resolution_mode": "reshuffle", "extension_days": 0}
    )
    assert response.status_code == 200, response.text
    assert response.json()["resolution_mode"] == "reshuffle"


def test_patch_required_column_cannot_be_null(client, setup):
    event_id = create(client, setup)["event_id"]
    response = client.patch(f"{BASE}/{event_id}", json={"event_date": None})
    assert response.status_code == 422
    assert error_fields(response) == ["event_date"]


def test_patch_and_delete_not_found(client, setup):
    assert client.patch(f"{BASE}/EVT-999", json={"requested_by": "Kaur"}).status_code == 404
    assert client.delete(f"{BASE}/EVT-999").status_code == 404


def test_delete(client, setup):
    event_id = create(client, setup)["event_id"]
    assert client.delete(f"{BASE}/{event_id}").status_code == 204
    assert client.get(f"{BASE}/{event_id}").status_code == 404
