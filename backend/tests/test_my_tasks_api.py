"""DIG-34 (DIG-153, DIG-154): blocker dan overrun oleh pelaksana task, PostgreSQL sungguhan."""

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text, update

from app.modules.auth.models import AppUser
from app.modules.data import my_task_service as service
from app.modules.data.models import Assignment, ChangeEvent, Holiday, Task
from tests.conftest import REQUIRES_DB, error_fields, make_token

DATA = "/api/v1/data"
MINE = f"{DATA}/my-tasks"
TODAY = date.today()
BACKEND = Path(__file__).resolve().parents[1]

pytestmark = REQUIRES_DB


def days_ago(count: int) -> date:
    return TODAY - timedelta(days=count)


def member(client, name: str) -> str:
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


def task(db, task_id, project_id, status="in_progress", finish=None):
    planned_finish = finish or TODAY + timedelta(days=10)
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
            estimated_days=5.0,
            phase="be_dev",
            planned_start=planned_finish - timedelta(days=6),
            planned_finish=planned_finish,
            actual_start=planned_finish - timedelta(days=6) if started else None,
            actual_finish=planned_finish if status == "done" else None,
            status=status,
        )
    )
    db.commit()


def assign(db, assignment_id, task_id, resource_id, released=None):
    db.add(
        Assignment(
            assignment_id=assignment_id,
            task_id=task_id,
            resource_id=resource_id,
            role_in_task="ROLE-BE",
            assigned_date=date(2026, 1, 5),
            released_date=released,
        )
    )
    db.commit()


def login_as(db, username: str, resource_id: str | None, roles=("anggota_tim",)) -> dict:
    token = make_token(db, username, list(roles))
    db.execute(update(AppUser).where(AppUser.username == username).values(resource_id=resource_id))
    db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def team(client, db) -> dict:
    response = client.post(
        f"{DATA}/projects",
        json={
            "project_name": "SIKEP",
            "process_owner": "Urusan Kepegawaian",
            "priority_rank": 1,
            "start_date": "2026-01-05",
            "target_launch_date": "2027-06-30",
            "status": "development",
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()["project_id"]
    sari, budi = member(client, "Sari"), member(client, "Budi")
    task(db, "TSK-0001", project)  # sedang dikerjakan Sari
    task(db, "TSK-0002", project, status="not_started")
    task(db, "TSK-0003", project, status="done")
    task(db, "TSK-0004", project)  # milik Budi
    task(db, "TSK-0005", project, finish=days_ago(7))  # lewat rencana
    assign(db, "ASG-0001", "TSK-0001", sari)
    assign(db, "ASG-0002", "TSK-0002", sari)
    assign(db, "ASG-0003", "TSK-0003", sari)
    assign(db, "ASG-0004", "TSK-0004", budi)
    assign(db, "ASG-0005", "TSK-0005", sari)
    return {
        "project": project,
        "sari": login_as(db, "sari", sari),
        "budi": login_as(db, "budi", budi),
    }


def status_of(db, task_id: str) -> str:
    db.expire_all()
    return db.scalar(select(Task.status).where(Task.task_id == task_id))


def record(client, headers, task_id="TSK-0001", **body):
    return client.post(
        f"{MINE}/{task_id}/events", headers=headers, json={"event_type": "blocker", **body}
    )


def resolve(client, headers, event_id, task_id="TSK-0001", **body):
    return client.post(f"{MINE}/{task_id}/events/{event_id}/resolve", headers=headers, json=body)


# --- GET /my-tasks ---


def test_my_tasks_lists_only_open_tasks_assigned_to_me(client, team):
    body = client.get(MINE, headers=team["sari"]).json()
    assert body["resource_name"] == "Sari"
    assert [t["task_id"] for t in body["tasks"]] == ["TSK-0005", "TSK-0001", "TSK-0002"]
    assert body["tasks"][0]["is_past_plan"] is True
    assert body["tasks"][1]["is_past_plan"] is False
    assert all(t["open_blocker"] is None and t["open_overrun"] is None for t in body["tasks"])


def test_released_assignment_is_not_mine_anymore(client, db, team):
    db.execute(
        update(Assignment)
        .where(Assignment.assignment_id == "ASG-0001")
        .values(released_date=days_ago(1))
    )
    db.commit()
    ids = [t["task_id"] for t in client.get(MINE, headers=team["sari"]).json()["tasks"]]
    assert "TSK-0001" not in ids
    assert record(client, team["sari"]).status_code == 403


def test_account_without_resource_gets_empty_list_and_cannot_record(client, db, team):
    headers = login_as(db, "tamu", None)
    body = client.get(MINE, headers=headers).json()
    assert (body["resource_id"], body["tasks"]) == (None, [])
    response = record(client, headers)
    assert response.status_code == 403
    assert "belum dihubungkan" in response.json()["detail"]


# --- blocker ---


def test_blocker_blocks_task_and_is_listed_as_open(client, db, team):
    response = record(client, team["sari"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["event_type"] == "blocker"
    assert body["event_date"] == TODAY.isoformat()
    assert (body["task_status"], body["task_status_changed"]) == ("blocked", True)
    assert status_of(db, "TSK-0001") == "blocked"

    event = db.get(ChangeEvent, body["event_id"])
    assert (event.project_id, event.affected_task_id) == (team["project"], "TSK-0001")
    assert event.requested_by == "Sari"
    assert (event.decision, event.resolution_mode) == (None, None)

    mine = {t["task_id"]: t for t in client.get(MINE, headers=team["sari"]).json()["tasks"]}
    assert mine["TSK-0001"]["open_blocker"]["event_id"] == body["event_id"]
    assert mine["TSK-0001"]["status"] == "blocked"


def test_blocker_on_task_not_started_is_recorded_without_status_change(client, db, team):
    response = record(client, team["sari"], "TSK-0002")
    assert response.status_code == 201, response.text
    assert response.json()["task_status_changed"] is False
    assert status_of(db, "TSK-0002") == "not_started"


def test_only_the_assignee_may_record(client, db, team):
    response = record(client, team["budi"])
    assert response.status_code == 403
    assert status_of(db, "TSK-0001") == "in_progress"
    assert db.scalar(select(ChangeEvent.event_id)) is None


def test_second_open_blocker_is_rejected(client, team):
    first = record(client, team["sari"]).json()["event_id"]
    response = record(client, team["sari"])
    assert response.status_code == 409
    assert first in response.json()["detail"]["msg"]


def test_closed_task_and_unknown_task(client, team):
    assert record(client, team["sari"], "TSK-0003").status_code == 409
    assert record(client, team["sari"], "TSK-9999").status_code == 404


def test_old_blocker_on_task_that_is_not_blocked_does_not_count_as_open(client, db, team):
    # Seperti dataset dosbim: ada kejadian blocker lama, tetapi task-nya tidak berstatus blocked.
    db.add(
        ChangeEvent(
            event_id="EVT-0001",
            project_id=team["project"],
            event_type="blocker",
            event_date=days_ago(30),
            requested_by="Kaur",
            affected_task_id="TSK-0001",
        )
    )
    db.commit()
    mine = {t["task_id"]: t for t in client.get(MINE, headers=team["sari"]).json()["tasks"]}
    assert mine["TSK-0001"]["open_blocker"] is None
    response = record(client, team["sari"])
    assert response.status_code == 201, response.text
    assert response.json()["event_id"] == "EVT-0002"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"event_type": "hotfix"}, "event_type"),
        ({"event_type": "blocker", "event_date": "besok"}, "event_date"),
        ({"event_type": "blocker", "event_date": "2999-01-01"}, "event_date"),
        ({"event_type": "blocker", "catatan": "x"}, "catatan"),
    ],
)
def test_bad_body_is_422(client, db, team, body, field):
    response = client.post(f"{MINE}/TSK-0001/events", headers=team["sari"], json=body)
    assert response.status_code == 422, response.text
    assert error_fields(response) == [field]
    assert status_of(db, "TSK-0001") == "in_progress"


def test_event_dated_before_i_was_assigned_is_rejected(client, db, team):
    # Sari ditugaskan 5 Januari 2026; sehari sebelumnya ia belum pelaksana task ini.
    response = record(client, team["sari"], event_date="2026-01-04")
    assert response.status_code == 403
    assert status_of(db, "TSK-0001") == "in_progress"


# --- menandai selesai ---


def test_resolving_blocker_fills_detail_and_resumes_task(client, db, team):
    event_id = record(client, team["sari"], event_date=days_ago(2).isoformat()).json()["event_id"]
    response = resolve(client, team["sari"], event_id)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resolved_date"] == TODAY.isoformat()
    assert (body["task_status"], body["task_status_changed"]) == ("in_progress", True)
    saved = db.execute(
        text("SELECT resolved_date FROM change_event_details WHERE event_id = :e"), {"e": event_id}
    ).scalar_one()
    assert saved == TODAY
    mine = {t["task_id"]: t for t in client.get(MINE, headers=team["sari"]).json()["tasks"]}
    assert mine["TSK-0001"]["open_blocker"] is None


def test_resolve_rules(client, team):
    event_id = record(client, team["sari"], event_date=days_ago(2).isoformat()).json()["event_id"]
    early = resolve(client, team["sari"], event_id, resolved_date=days_ago(3).isoformat())
    assert early.status_code == 422
    assert error_fields(early) == ["resolved_date"]
    future = resolve(
        client, team["sari"], event_id, resolved_date=(TODAY + timedelta(days=1)).isoformat()
    )
    assert error_fields(future) == ["resolved_date"]
    assert resolve(client, team["budi"], event_id).status_code == 403
    assert resolve(client, team["sari"], "EVT-9999").status_code == 404
    assert resolve(client, team["sari"], event_id, "TSK-0002").status_code == 404  # task lain
    assert resolve(client, team["sari"], event_id).status_code == 200
    assert resolve(client, team["sari"], event_id).status_code == 409  # sudah selesai


def test_resolve_keeps_approval_already_stored_in_detail(client, db, team):
    event_id = record(client, team["sari"], event_date=days_ago(2).isoformat()).json()["event_id"]
    db.execute(
        text("INSERT INTO change_event_details (event_id, approved_date) VALUES (:e, :a)"),
        {"e": event_id, "a": days_ago(1)},
    )
    db.commit()
    assert resolve(client, team["sari"], event_id).status_code == 200
    row = db.execute(
        text("SELECT approved_date, resolved_date FROM change_event_details WHERE event_id = :e"),
        {"e": event_id},
    ).one()
    assert tuple(row) == (days_ago(1), TODAY)


# --- overrun manual ---


def test_overrun_is_recorded_without_touching_status(client, db, team):
    response = record(client, team["sari"], "TSK-0005", event_type="overrun")
    assert response.status_code == 201, response.text
    assert response.json()["task_status_changed"] is False
    assert status_of(db, "TSK-0005") == "in_progress"
    mine = {t["task_id"]: t for t in client.get(MINE, headers=team["sari"]).json()["tasks"]}
    assert mine["TSK-0005"]["open_overrun"]["event_id"] == response.json()["event_id"]
    assert record(client, team["sari"], "TSK-0005", event_type="overrun").status_code == 409
    # Blocker tetap boleh dicatat pada task yang sama.
    assert record(client, team["sari"], "TSK-0005").status_code == 201


def test_resolving_overrun_does_not_change_status(client, db, team):
    event_id = record(client, team["sari"], "TSK-0005", event_type="overrun").json()["event_id"]
    response = resolve(client, team["sari"], event_id, "TSK-0005")
    assert response.status_code == 200, response.text
    assert response.json()["task_status_changed"] is False
    assert status_of(db, "TSK-0005") == "in_progress"


# --- deteksi overrun otomatis (DIG-154) ---


def overruns(db) -> dict[str, ChangeEvent]:
    db.expire_all()
    rows = db.scalars(select(ChangeEvent).where(ChangeEvent.event_type == "overrun"))
    return {event.affected_task_id: event for event in rows}


def test_detection_creates_one_overrun_per_late_open_task(client, db, team):
    task(db, "TSK-0006", team["project"], status="done", finish=days_ago(20))
    task(db, "TSK-0007", team["project"], status="dropped", finish=days_ago(20))
    task(db, "TSK-0008", team["project"], status="on_hold", finish=days_ago(20))
    task(db, "TSK-0009", team["project"], finish=TODAY)  # jatuh tempo hari ini, belum lewat
    response = client.post(f"{DATA}/overrun-detection")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["as_of"] == TODAY.isoformat()
    assert body["created_count"] == 2
    found = overruns(db)
    assert sorted(found) == ["TSK-0005", "TSK-0008"]
    event = found["TSK-0005"]
    assert event.requested_by == "Sistem"
    assert event.project_id == team["project"]
    assert days_ago(7) < event.event_date <= TODAY
    assert event.event_date.weekday() < 5 or event.event_date == TODAY
    assert status_of(db, "TSK-0005") == "in_progress"


def test_dry_run_counts_without_saving(client, db, team):
    body = client.post(f"{DATA}/overrun-detection", params={"dry_run": True}).json()
    assert (body["dry_run"], body["created_count"]) == (True, 1)
    assert (body["task_ids"], body["event_ids"]) == (["TSK-0005"], [])
    assert overruns(db) == {}
    # Kunci baris sudah dilepas, jadi proses sungguhan sesudahnya tetap jalan.
    real = client.post(f"{DATA}/overrun-detection").json()
    assert (real["dry_run"], real["created_count"]) == (False, 1)


def test_detection_is_idempotent(client, db, team):
    assert client.post(f"{DATA}/overrun-detection").json()["created_count"] == 1
    second = client.post(f"{DATA}/overrun-detection").json()
    assert (second["created_count"], second["event_ids"]) == (0, [])
    assert len(overruns(db)) == 1


def test_detection_skips_task_with_overrun_recorded_by_member(client, db, team):
    record(client, team["sari"], "TSK-0005", event_type="overrun")
    assert client.post(f"{DATA}/overrun-detection").json()["created_count"] == 0


def test_detection_dates_overrun_on_first_working_day_after_plan(db, team):
    # Rencana selesai Jumat 6 Maret 2026, Senin 9 Maret libur: overrun mulai Selasa 10 Maret.
    task(db, "TSK-0010", team["project"], finish=date(2026, 3, 6))
    db.add(Holiday(holiday_date=date(2026, 3, 9), holiday_name="Libur uji"))
    db.commit()
    outcome = service.detect_overruns(db, date(2026, 3, 20))
    assert outcome.created_count == 1  # TSK-0005 belum lewat rencana pada tanggal acuan itu
    assert overruns(db)["TSK-0010"].event_date == date(2026, 3, 10)


def test_detection_ids_continue_after_existing_events(client, db, team):
    record(client, team["sari"])  # EVT-001
    ids = client.post(f"{DATA}/overrun-detection").json()["event_ids"]
    assert ids == ["EVT-002"]


def test_cli_runs_standalone_and_rejects_bad_date():
    # Proses terpisah supaya model yang sudah dimuat pytest tidak ikut menolong.
    result = subprocess.run(
        [sys.executable, "-m", "app.modules.data.detect_overruns", "--as-of", "kemarin"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1, result.stderr
    assert "YYYY-MM-DD" in result.stderr
