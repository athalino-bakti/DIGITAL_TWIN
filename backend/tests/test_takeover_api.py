"""DIG-35 (DIG-157, DIG-158, DIG-159): pengalihan task terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest
from sqlalchemy import select

from app.modules.data.models import Assignment, Task
from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

DATA = "/api/v1/data"


def member(client, name, role, secondary=(), cross=False, joined="2024-01-01") -> str:
    response = client.post(
        f"{DATA}/resources",
        json={
            "resource_name": name,
            "primary_role_id": role,
            "secondary_role_ids": list(secondary),
            "cross_role_capable": cross,
            "join_date": joined,
            "seniority": "mid",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["resource_id"]


def absence(client, resource_id, start, end, kind="sudden_leave") -> str:
    response = client.post(
        f"{DATA}/availability",
        json={
            "resource_id": resource_id,
            "date_start": start,
            "date_end": end,
            "absence_type": kind,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["availability_id"]


def task(db, task_id, project_id, role="ROLE-BE", status="in_progress", start=(2026, 3, 2)):
    db.add(
        Task(
            task_id=task_id,
            project_id=project_id,
            feature_name="Cuti",
            task_name=f"Task {task_id}",
            required_role_id=role,
            complexity_id="CX-M",
            priority_rank=1,
            estimated_days=5.0,
            phase="be_dev",
            planned_start=date(*start),
            planned_finish=date(start[0], start[1], start[2] + 9),
            status=status,
        )
    )
    db.commit()


def assign(db, assignment_id, task_id, resource_id, assigned=date(2026, 3, 2), role="ROLE-BE"):
    db.add(
        Assignment(
            assignment_id=assignment_id,
            task_id=task_id,
            resource_id=resource_id,
            role_in_task=role,
            assigned_date=assigned,
        )
    )
    db.commit()


@pytest.fixture
def team(client, db) -> dict:
    response = client.post(
        f"{DATA}/projects",
        json={
            "project_name": "SIKEP",
            "process_owner": "Urusan Kepegawaian",
            "priority_rank": 1,
            "start_date": "2026-01-05",
            "target_launch_date": "2026-06-30",
            "status": "development",
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()["project_id"]
    ids = {
        "project": project,
        "sari": member(client, "Sari", "ROLE-BE"),  # pelaksana awal
        "budi": member(client, "Budi", "ROLE-BE"),  # peran utama sama
        "citra": member(client, "Citra", "ROLE-FE", secondary=["ROLE-BE"]),  # peran rangkap
        "dodi": member(client, "Dodi", "ROLE-QA", cross=True),  # lintas peran
        "eka": member(client, "Eka", "ROLE-FE"),  # tidak cocok
        "fajar": member(client, "Fajar", "ROLE-BE", joined="2026-04-01"),  # belum bergabung
    }
    task(db, "TSK-0001", project)
    task(db, "TSK-0002", project, status="done")
    task(db, "TSK-0003", project, start=(2026, 5, 4))
    assign(db, "ASG-0001", "TSK-0001", ids["sari"])
    assign(db, "ASG-0002", "TSK-0002", ids["sari"])
    assign(db, "ASG-0003", "TSK-0003", ids["sari"])
    assign(db, "ASG-0004", "TSK-0003", ids["budi"])  # Budi sudah punya 1 penugasan aktif
    return ids


# --- DIG-159 kandidat pengganti ---


def candidates(client, task_id="TSK-0001", on="2026-03-09") -> list[tuple[str, str]]:
    response = client.get(f"{DATA}/tasks/{task_id}/replacement-candidates", params={"on": on})
    assert response.status_code == 200, response.text
    return [(c["resource_name"], c["match"]) for c in response.json()]


def test_candidates_ordered_by_match_then_load(client, team):
    assert candidates(client) == [("Budi", "primary"), ("Citra", "secondary"), ("Dodi", "cross")]


def test_candidates_skip_absent_members(client, team):
    absence(client, team["budi"], "2026-03-09", "2026-03-11", "planned_leave")
    assert [name for name, _ in candidates(client)] == ["Citra", "Dodi"]
    # rotation_in berarti hadir, jadi tidak menyaring
    absence(client, team["citra"], "2026-03-09", "2026-03-09", "rotation_in")
    assert [name for name, _ in candidates(client)] == ["Citra", "Dodi"]


def test_candidates_include_members_after_join_date(client, team):
    names = [name for name, _ in candidates(client, on="2026-04-02")]
    assert "Fajar" in names and "Sari" not in names


def test_candidates_unknown_task(client, team):
    assert client.get(f"{DATA}/tasks/TSK-9999/replacement-candidates").status_code == 404


# --- DIG-158 pengalihan ---


def take_over(client, to, day="2026-03-09", frm=None, task_id="TSK-0001"):
    return client.post(
        f"{DATA}/tasks/{task_id}/takeover",
        json={"from_resource_id": frm, "to_resource_id": to, "takeover_date": day},
    )


def test_takeover_closes_old_and_creates_new_in_one_go(client, db, team):
    response = take_over(client, team["citra"], frm=team["sari"])
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["released"]["assignment_id"] == "ASG-0001"
    assert result["released"]["released_date"] == "2026-03-09"
    assert result["created"] == {
        "assignment_id": "ASG-0005",
        "task_id": "TSK-0001",
        "resource_id": team["citra"],
        "resource_name": "Citra",
        "role_in_task": "ROLE-BE",
        "assigned_date": "2026-03-09",
        "released_date": None,
        "is_takeover": True,
    }
    history = client.get(f"{DATA}/tasks/TSK-0001/assignments").json()
    assert [(a["resource_name"], a["is_takeover"]) for a in history] == [
        ("Sari", False),
        ("Citra", True),
    ]
    # Sari tidak lagi aktif di task ini, jadi muncul lagi sebagai kandidat; Citra tidak.
    names = [name for name, _ in candidates(client, on="2026-03-10")]
    assert "Sari" in names and "Citra" not in names


@pytest.mark.parametrize(
    "case,expected",
    [
        ("from_not_assigned", ["from_resource_id"]),
        ("before_assigned", ["takeover_date"]),
        ("same_person", ["to_resource_id"]),
        ("role_mismatch", ["to_resource_id"]),
        ("unknown_member", ["to_resource_id"]),
        ("not_joined", ["to_resource_id"]),
    ],
)
def test_takeover_rules(client, db, team, case, expected):
    frm, to, day = team["sari"], team["budi"], "2026-03-09"
    if case == "from_not_assigned":
        frm = team["citra"]
    elif case == "before_assigned":
        day = "2026-03-01"
    elif case == "same_person":
        to = team["sari"]
    elif case == "role_mismatch":
        to = team["eka"]
    elif case == "unknown_member":
        to = "RES-999"
    elif case == "not_joined":
        to = team["fajar"]
    response = take_over(client, to, day=day, frm=frm)
    assert response.status_code == 422, response.text
    assert error_fields(response) == expected
    # tidak ada yang berubah
    old = db.scalar(select(Assignment).where(Assignment.assignment_id == "ASG-0001"))
    db.refresh(old)
    assert old.released_date is None


def test_takeover_rejects_absent_replacement(client, team):
    avl = absence(client, team["budi"], "2026-03-09", "2026-03-11")
    response = take_over(client, team["budi"], frm=team["sari"])
    assert response.status_code == 422
    assert avl in response.json()["detail"][0]["msg"]


def test_takeover_rejects_member_already_on_task(client, team):
    response = take_over(client, team["budi"], frm=team["sari"], task_id="TSK-0003")
    assert response.status_code == 422
    assert error_fields(response) == ["to_resource_id"]


def test_takeover_unknown_task_and_bad_body(client, team):
    assert take_over(client, team["budi"], frm=team["sari"], task_id="TSK-9999").status_code == 404
    response = take_over(client, team["budi"], frm=team["sari"], day="09/03/2026")
    assert response.status_code == 422
    assert error_fields(response) == ["takeover_date"]


# --- DIG-157 task terdampak ---


def test_affected_tasks_of_sudden_leave(client, team):
    avl = absence(client, team["sari"], "2026-03-09", "2026-03-10")
    affected = client.get(f"{DATA}/availability/{avl}/affected-tasks").json()
    # TSK-0002 sudah done, TSK-0003 baru mulai Mei
    assert [(t["task_id"], t["assignment_id"]) for t in affected] == [("TSK-0001", "ASG-0001")]
    assert affected[0]["project_name"] == "SIKEP"


def test_affected_tasks_after_takeover_and_rotation_in(client, team):
    take_over(client, team["budi"], frm=team["sari"], day="2026-03-05")
    avl = absence(client, team["sari"], "2026-03-09", "2026-03-10")
    assert client.get(f"{DATA}/availability/{avl}/affected-tasks").json() == []
    rotation = absence(client, team["budi"], "2026-03-09", "2026-03-10", "rotation_in")
    assert client.get(f"{DATA}/availability/{rotation}/affected-tasks").json() == []
    assert client.get(f"{DATA}/availability/AVL-999/affected-tasks").status_code == 404
