"""DIG-42 (DIG-182, DIG-185): graf dependency dan jalur kritis terhadap PostgreSQL sungguhan."""

from datetime import date, timedelta

import pytest

from app.modules.data.models import Holiday, Task, TaskDependency
from tests.conftest import REQUIRES_DB, error_fields, make_token

pytestmark = REQUIRES_DB

URL = "/api/v1/digital-twin/dependency"
AS_OF = "2026-03-13"  # Jumat


def project(client, name="SIKEP", rank=1) -> str:
    response = client.post(
        "/api/v1/data/projects",
        json={
            "project_name": name,
            "process_owner": "Urusan Kepegawaian",
            "priority_rank": rank,
            "start_date": "2026-01-05",
            "target_launch_date": "2026-06-30",
            "status": "development",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["project_id"]


def task(db, task_id, project_id, days, finish=(2026, 3, 31), status="not_started", actual=None):
    planned_finish = date(*finish)
    db.add(
        Task(
            task_id=task_id,
            project_id=project_id,
            feature_name="Cuti",
            task_name=f"Task {task_id}",
            required_role_id="ROLE-BE",
            complexity_id="CX-M",
            priority_rank=1,
            estimated_days=days,
            phase="be_dev",
            planned_start=planned_finish - timedelta(days=4),
            planned_finish=planned_finish,
            actual_start=planned_finish - timedelta(days=4) if actual else None,
            actual_finish=actual,
            status=status,
        )
    )
    db.commit()


def link(db, dependency_id, before, after, kind="hard", factor=1.0):
    db.add(
        TaskDependency(
            dependency_id=dependency_id,
            task_id=after,
            depends_on_task_id=before,
            dependency_type=kind,
            propagation_factor=factor,
        )
    )
    db.commit()


@pytest.fixture
def graph(client, db) -> str:
    """A(3) -> B(5) -> D(2) jalur kritis 10 hari; A -> C(2) -> D kelonggaran 3; C ~> E soft.

    A terlambat: planned_finish Senin 9 Maret, belum selesai pada Jumat 13 Maret (4 hari kerja).
    """
    pid = project(client)
    task(db, "TSK-0001", pid, 3.0, finish=(2026, 3, 9), status="in_progress")
    task(db, "TSK-0002", pid, 5.0)
    task(db, "TSK-0003", pid, 2.0)
    task(db, "TSK-0004", pid, 2.0)
    task(db, "TSK-0005", pid, 1.0)
    link(db, "DEP-0001", "TSK-0001", "TSK-0002")
    link(db, "DEP-0002", "TSK-0001", "TSK-0003")
    link(db, "DEP-0003", "TSK-0002", "TSK-0004")
    link(db, "DEP-0004", "TSK-0003", "TSK-0004")
    link(db, "DEP-0005", "TSK-0003", "TSK-0005", kind="soft", factor=0.3)
    return pid


def fetch(client, project_id, **params) -> dict:
    response = client.get(URL, params={"project_id": project_id, "as_of": AS_OF, **params})
    assert response.status_code == 200, response.text
    return response.json()


def nodes(body) -> dict[str, dict]:
    return {node["task_id"]: node for node in body["nodes"]}


def test_critical_path_and_float(client, graph):
    body = fetch(client, graph)
    assert body["project_duration"] == 10
    assert body["critical_task_ids"] == ["TSK-0001", "TSK-0002", "TSK-0004"]
    assert body["cycle_task_ids"] == []
    assert body["focus"] is None
    by_id = nodes(body)
    assert {k: v["is_critical"] for k, v in by_id.items()} == {
        "TSK-0001": True,
        "TSK-0002": True,
        "TSK-0003": False,
        "TSK-0004": True,
        "TSK-0005": False,
    }
    side = by_id["TSK-0003"]
    assert (side["earliest_start"], side["earliest_finish"]) == (3, 5)
    assert (side["latest_start"], side["latest_finish"]) == (6, 8)
    assert side["total_float"] == 3
    assert all(node["impact_days"] is None for node in body["nodes"])


def test_edges_carry_type_factor_and_critical_flag(client, graph):
    edges = {edge["dependency_id"]: edge for edge in fetch(client, graph)["edges"]}
    assert {k: v["is_critical"] for k, v in edges.items()} == {
        "DEP-0001": True,
        "DEP-0002": False,
        "DEP-0003": True,
        "DEP-0004": False,
        "DEP-0005": False,
    }
    soft = edges["DEP-0005"]
    assert soft["dependency_type"] == "soft"
    assert soft["propagation_factor"] == 0.3
    assert (soft["depends_on_task_id"], soft["task_id"]) == ("TSK-0003", "TSK-0005")


def test_soft_dependency_does_not_shift_schedule(client, graph):
    # E hanya bergantung soft pada C, jadi boleh mulai di hari ke-0.
    assert nodes(fetch(client, graph))["TSK-0005"]["earliest_start"] == 0


def test_late_task_is_flagged_with_working_days(client, graph):
    by_id = nodes(fetch(client, graph))
    assert by_id["TSK-0001"]["is_late"] is True
    assert by_id["TSK-0001"]["delay_working_days"] == 4  # Selasa sampai Jumat
    assert by_id["TSK-0002"]["is_late"] is False
    assert by_id["TSK-0002"]["delay_working_days"] == 0


def test_holiday_is_not_counted_as_delay(client, db, graph):
    db.add(Holiday(holiday_date=date(2026, 3, 11), holiday_name="Libur uji"))
    db.commit()
    assert nodes(fetch(client, graph))["TSK-0001"]["delay_working_days"] == 3


def test_focus_propagates_own_delay_times_factor(client, graph):
    body = fetch(client, graph, task_id="TSK-0001")
    assert body["focus"] == {"task_id": "TSK-0001", "delay_days": 4, "affected_count": 4}
    impact = {k: v["impact_days"] for k, v in nodes(body).items()}
    assert impact == {
        "TSK-0001": None,  # sumbernya sendiri bukan "terdampak"
        "TSK-0002": 4,
        "TSK-0003": 4,
        "TSK-0004": 4,
        "TSK-0005": 1.2,  # 4 x 0,3
    }


def test_focus_delay_can_be_overridden(client, graph):
    body = fetch(client, graph, task_id="TSK-0003", delay_days=10)
    assert body["focus"] == {"task_id": "TSK-0003", "delay_days": 10, "affected_count": 2}
    impact = {k: v["impact_days"] for k, v in nodes(body).items() if v["impact_days"] is not None}
    assert impact == {"TSK-0004": 10, "TSK-0005": 3}


def test_focus_on_task_that_is_not_late_affects_nothing(client, graph):
    body = fetch(client, graph, task_id="TSK-0002")
    assert body["focus"] == {"task_id": "TSK-0002", "delay_days": 0, "affected_count": 0}


def test_finished_task_stops_propagation(client, db, graph):
    done = db.get(Task, "TSK-0002")
    done.status = "done"
    done.actual_start, done.actual_finish = date(2026, 3, 2), date(2026, 3, 12)
    db.commit()
    impact = {
        k: v["impact_days"] for k, v in nodes(fetch(client, graph, task_id="TSK-0001")).items()
    }
    assert impact["TSK-0002"] is None
    assert impact["TSK-0004"] == 4  # masih kena lewat TSK-0003


def test_done_task_judged_by_actual_finish_and_dropped_never_late(client, db, graph):
    task(db, "TSK-0006", graph, 1.0, finish=(2026, 3, 9), status="done", actual=date(2026, 3, 10))
    task(db, "TSK-0007", graph, 1.0, finish=(2026, 3, 9), status="done", actual=date(2026, 3, 9))
    task(db, "TSK-0008", graph, 1.0, finish=(2026, 3, 9), status="dropped")
    by_id = nodes(fetch(client, graph))
    assert by_id["TSK-0006"]["delay_working_days"] == 1
    assert by_id["TSK-0007"]["is_late"] is False
    assert by_id["TSK-0008"]["is_late"] is False


def test_cycle_is_reported_instead_of_crashing(client, db, graph):
    link(db, "DEP-0006", "TSK-0004", "TSK-0001")
    body = fetch(client, graph, task_id="TSK-0001")
    assert set(body["cycle_task_ids"]) >= {"TSK-0001", "TSK-0002", "TSK-0004"}
    assert body["critical_task_ids"] == []
    assert body["project_duration"] == 0
    assert len(body["nodes"]) == 5
    assert len(body["edges"]) == 6


def test_only_tasks_and_edges_of_the_project(client, db, graph):
    other = project(client, "SIMAK", rank=2)
    task(db, "TSK-0101", other, 20.0)
    task(db, "TSK-0102", other, 1.0)
    link(db, "DEP-0101", "TSK-0101", "TSK-0102")
    body = fetch(client, graph)
    assert len(body["nodes"]) == 5
    assert len(body["edges"]) == 5
    assert body["project_duration"] == 10
    assert fetch(client, other)["project_duration"] == 21


def test_project_without_tasks(client):
    body = fetch(client, project(client))
    assert (body["nodes"], body["edges"], body["critical_task_ids"]) == ([], [], [])
    assert body["project_duration"] == 0


def test_unknown_project_is_404(client):
    assert client.get(URL, params={"project_id": "PRJ-999"}).status_code == 404


def test_focus_task_from_other_project_is_rejected(client, db, graph):
    other = project(client, "SIMAK", rank=2)
    task(db, "TSK-0101", other, 1.0)
    response = client.get(URL, params={"project_id": graph, "task_id": "TSK-0101"})
    assert response.status_code == 422
    assert error_fields(response) == ["task_id"]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"project_id": "proyek"},
        {"project_id": "PRJ-001", "task_id": "x"},
        {"project_id": "PRJ-001", "delay_days": -1},
        {"project_id": "PRJ-001", "as_of": "kemarin"},
    ],
)
def test_bad_query_is_422(client, params):
    assert client.get(URL, params=params).status_code == 422


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
def test_permission_per_role(client, db, graph, role, expected):
    headers = {"Authorization": f"Bearer {make_token(db, f'uji_{role}', [role])}"}
    assert client.get(URL, params={"project_id": graph}, headers=headers).status_code == expected


def test_requires_login(client, graph):
    del client.headers["Authorization"]
    assert client.get(URL, params={"project_id": graph}).status_code == 401
