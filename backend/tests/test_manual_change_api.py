"""DIG-162: perubahan task dari aplikasi tercatat di task_manual_change (PostgreSQL)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select, update

from app.modules.auth.models import AppUser
from app.modules.data import manual_change
from app.modules.data.manual_change_models import TaskManualChange
from app.modules.data.models import Assignment, ChangeEvent, Task
from tests.conftest import REQUIRES_DB, make_token

pytestmark = REQUIRES_DB

DATA = "/api/v1/data"
TODAY = date.today()


def project(client) -> str:
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
    return response.json()["project_id"]


def task(db, task_id, project_id, status="in_progress"):
    finish = TODAY + timedelta(days=10)
    db.add(
        Task(
            task_id=task_id,
            project_id=project_id,
            feature_name="Cuti",
            task_name=f"Task {task_id}",
            required_role_id="ROLE-BE",
            complexity_id="CX-M",
            priority_rank=3,
            estimated_days=5.0,
            phase="be_dev",
            planned_start=finish - timedelta(days=6),
            planned_finish=finish,
            actual_start=finish - timedelta(days=6),
            status=status,
        )
    )
    db.commit()


def changes(db, task_id) -> list[TaskManualChange]:
    db.expire_all()
    return list(
        db.scalars(
            select(TaskManualChange)
            .where(TaskManualChange.task_id == task_id)
            .order_by(TaskManualChange.change_id)
        )
    )


@pytest.fixture
def setup(client, db) -> dict:
    pid = project(client)
    task(db, "TSK-0001", pid)
    task(db, "TSK-0002", pid, status="in_qa")
    response = client.post(
        f"{DATA}/resources",
        json={
            "resource_name": "Sari",
            "primary_role_id": "ROLE-BE",
            "secondary_role_ids": [],
            "cross_role_capable": False,
            "join_date": "2024-01-01",
            "seniority": "mid",
        },
    )
    sari = response.json()["resource_id"]
    for i, tid in enumerate(["TSK-0001", "TSK-0002"], start=1):
        db.add(
            Assignment(
                assignment_id=f"ASG-000{i}",
                task_id=tid,
                resource_id=sari,
                role_in_task="ROLE-BE",
                assigned_date=date(2026, 1, 5),
            )
        )
    db.commit()
    token = make_token(db, "sari", ["anggota_tim"])
    db.execute(update(AppUser).where(AppUser.username == "sari").values(resource_id=sari))
    db.commit()
    user_id = db.scalar(select(AppUser.user_id).where(AppUser.username == "sari"))
    return {"project": pid, "sari": {"Authorization": f"Bearer {token}"}, "sari_id": user_id}


def test_change_request_effect_is_recorded(client, db, setup):
    response = client.post(
        f"{DATA}/change-events",
        json={
            "project_id": setup["project"],
            "event_type": "change_request",
            "event_date": TODAY.isoformat(),
            "decision": "accept_now",
            "resolution_mode": "reshuffle",
            "affected_task_id": "TSK-0001",
            "task_effect": {"status": "on_hold", "priority_rank": 7},
        },
    )
    assert response.status_code == 201, response.text
    event_id = response.json()["event_id"]
    rows = changes(db, "TSK-0001")
    assert [(r.field, r.old_value, r.new_value, r.source, r.ref) for r in rows] == [
        ("status", "in_progress", "on_hold", "change_event", event_id),
        ("priority_rank", "3", "7", "change_event", event_id),
    ]
    assert all(r.changed_by is not None and r.resolution is None for r in rows)


def test_event_without_effect_records_nothing(client, db, setup):
    response = client.post(
        f"{DATA}/change-events",
        json={
            "project_id": setup["project"],
            "event_type": "change_request",
            "event_date": TODAY.isoformat(),
            "affected_task_id": "TSK-0001",
        },
    )
    assert response.status_code == 201, response.text
    assert changes(db, "TSK-0001") == []


def test_blocker_restores_in_qa_and_records_both_changes(client, db, setup):
    headers = setup["sari"]
    record = client.post(
        f"{DATA}/my-tasks/TSK-0002/events", headers=headers, json={"event_type": "blocker"}
    )
    assert record.status_code == 201, record.text
    event_id = record.json()["event_id"]
    resolve = client.post(
        f"{DATA}/my-tasks/TSK-0002/events/{event_id}/resolve", headers=headers, json={}
    )
    assert resolve.status_code == 200, resolve.text
    # Sebelumnya selalu in_progress; sekarang kembali ke status sebelum blocker.
    assert resolve.json()["task_status"] == "in_qa"
    rows = changes(db, "TSK-0002")
    assert [(r.old_value, r.new_value, r.ref) for r in rows] == [
        ("in_qa", "blocked", event_id),
        ("blocked", "in_qa", event_id),
    ]
    assert {r.changed_by for r in rows} == {setup["sari_id"]}


def test_old_blocker_without_record_falls_back_to_in_progress(client, db, setup):
    db.execute(update(Task).where(Task.task_id == "TSK-0002").values(status="blocked"))
    db.commit()
    record = client.post(
        f"{DATA}/my-tasks/TSK-0002/events", headers=setup["sari"], json={"event_type": "blocker"}
    )
    event_id = record.json()["event_id"]
    # Task sudah blocked dari data impor, jadi tidak ada status sebelumnya yang tercatat.
    assert changes(db, "TSK-0002") == []
    resolve = client.post(
        f"{DATA}/my-tasks/TSK-0002/events/{event_id}/resolve", headers=setup["sari"], json={}
    )
    assert resolve.json()["task_status"] == "in_progress"


def test_open_changes_and_settle(client, db, setup):
    client.post(
        f"{DATA}/my-tasks/TSK-0001/events", headers=setup["sari"], json={"event_type": "blocker"}
    )
    pending = manual_change.open_changes(db, ["TSK-0001", "TSK-0002"])
    assert set(pending) == {"TSK-0001"}
    status = pending["TSK-0001"]["status"]
    assert (status.new_value, status.source, len(status.change_ids)) == ("blocked", "blocker", 1)

    # Impor membawa in_progress, padahal task sedang blocked dari aplikasi: konflik.
    task_row = db.get(Task, "TSK-0001")
    result = manual_change.merge_task_import(
        {"status": task_row.status}, {"status": "in_progress"}, pending["TSK-0001"]
    )
    assert [c.field for c in result.conflicts] == ["status"]

    assert manual_change.settle(db, status.change_ids, "kept") == 1
    db.commit()
    assert manual_change.open_changes(db, ["TSK-0001"]) == {}
    [row] = changes(db, "TSK-0001")
    assert (row.resolution, row.resolved_at is not None) == ("kept", True)


def test_changes_are_deleted_with_their_task(client, db, setup):
    client.post(
        f"{DATA}/my-tasks/TSK-0001/events", headers=setup["sari"], json={"event_type": "blocker"}
    )
    assert len(changes(db, "TSK-0001")) == 1
    # FK ON DELETE CASCADE: hapus dulu baris yang menahan task (D-10), lalu task-nya.
    db.execute(ChangeEvent.__table__.delete())
    db.execute(Assignment.__table__.delete().where(Assignment.task_id == "TSK-0001"))
    db.execute(Task.__table__.delete().where(Task.task_id == "TSK-0001"))
    db.commit()
    assert changes(db, "TSK-0001") == []
