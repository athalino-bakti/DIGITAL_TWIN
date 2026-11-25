"""DIG-134: ETL staging ke tasks, task_dependencies, assignments terhadap PostgreSQL sungguhan."""

from datetime import date

import pytest
from sqlalchemy import func, select, text

from app.modules.data.audit_models import AuditLog
from app.modules.data.etl.load import run_project
from app.modules.data.import_job_models import ImportJob
from app.modules.data.manual_change_models import TaskManualChange
from app.modules.data.models import Assignment, Task, TaskDependency
from app.modules.data.quality_models import DataQualityResult, RejectedRow
from app.modules.data.resource_alias_service import alias_key
from app.modules.data.staging_models import StagingProjectPlan
from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB

DATA = "/api/v1/data"
ROW = {
    "feature_name": "Cuti",
    "role_label": "ROLE-BE",
    "complexity_label": "Medium",
    "priority": "1",
    "estimated_days": "3",
    "planned_start": "02/11/2026",
    "planned_finish": "04/11/2026",
    "actual_start": "",
    "actual_finish": "",
    "status_label": "Dikerjakan",
    "depends_on": "",
    "notes": "",
}


def project(client, name="SIKEP", rank=1) -> str:
    response = client.post(
        f"{DATA}/projects",
        json={
            "project_name": name,
            "process_owner": "Urusan Kepegawaian",
            "priority_rank": rank,
            "start_date": "2026-10-01",
            "target_launch_date": "2026-12-31",
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


def batch(db, project_id, rows) -> int:
    job = ImportJob(
        source="project_plan", trigger="manual", status="succeeded", finished_at=func.now()
    )
    db.add(job)
    db.flush()
    for number, values in enumerate(rows, start=2):
        db.add(
            StagingProjectPlan(
                import_job_id=job.job_id,
                row_number=number,
                project_id=project_id,
                file_name="plan.csv",
                raw=values,
                **values,
            )
        )
    db.commit()
    return job.job_id


@pytest.fixture
def setup(client, db) -> dict:
    db.execute(text("TRUNCATE audit_log, resource_alias, staging_trello_action RESTART IDENTITY"))
    db.execute(text("TRUNCATE import_job CASCADE"))
    db.commit()
    pid = project(client)
    sari = member(client, "Sari Puspitasari")
    db.execute(
        text(
            "INSERT INTO resource_alias (resource_id, source, alias, alias_key) "
            "VALUES (:r, 'project_plan', 'Sari Puspitasari', :k)"
        ),
        {"r": sari, "k": alias_key("project_plan", "Sari Puspitasari")},
    )
    rows = [
        ROW | {"task_code": "TSK-0001", "task_name": "API cuti", "pic": "Sari Puspitasari",
               "depends_on": "TSK-0002"},
        ROW | {"task_code": "TSK-0002", "task_name": "Skema cuti", "pic": "Orang Asing"},
        ROW | {"task_code": "TSK-0003", "task_name": "Rusak", "pic": "", "planned_start": "5 Nov"},
    ]  # fmt: skip
    job = batch(db, pid, rows)
    return {"project": pid, "sari": sari, "job": job, "rows": rows}


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_first_run_loads_valid_rows_and_rejects_dirty_ones(db, setup):
    report = run_project(db, setup["project"])
    db.commit()
    assert report.job_id == setup["job"]
    assert sorted(db.scalars(select(Task.task_id))) == ["TSK-0001", "TSK-0002"]  # TSK-0003 ditolak
    assert report.rejected["tasks"] == 1
    dep = db.scalar(select(TaskDependency))
    assert (dep.task_id, dep.depends_on_task_id, dep.dependency_type, dep.propagation_factor) == (
        "TSK-0001",
        "TSK-0002",
        "hard",
        1.0,
    )
    (assignment,) = db.scalars(select(Assignment))  # PIC asing ditolak (resource_id kosong)
    assert (assignment.task_id, assignment.resource_id, assignment.assigned_date) == (
        "TSK-0001",
        setup["sari"],
        date(2026, 11, 2),
    )
    assert report.rejected["assignments"] == 1
    assert any(p["value"] == "Orang Asing" for p in report.problems)
    task = db.get(Task, "TSK-0001")
    assert (task.status, task.phase, task.estimated_days) == ("in_progress", "be_dev", 3.0)
    assert count(db, AuditLog) == 2 + 1 + 1
    assert {a.source for a in db.scalars(select(AuditLog))} == {"etl"}
    assert db.get(ImportJob, setup["job"]).details["etl"]["inserted"]["tasks"] == 2
    # Hasil validasi tersimpan untuk laporan kualitas (DIG-146) pada job batch yang sama.
    rejected = db.scalars(
        select(RejectedRow).where(RejectedRow.job_id == setup["job"], RejectedRow.level == "tolak")
    ).all()
    assert {r.row_key for r in rejected if r.table_name == "tasks"} == {"TSK-0003"}
    assert count(db, DataQualityResult) > 0


def test_second_run_changes_nothing(db, setup):
    run_project(db, setup["project"])
    db.commit()
    audits = count(db, AuditLog)
    again = run_project(db, setup["project"])
    db.commit()
    assert dict(again.inserted) == {} and dict(again.updated) == {}
    assert again.unchanged["tasks"] == 2
    assert (count(db, Task), count(db, TaskDependency), count(db, Assignment)) == (2, 1, 1)
    assert count(db, AuditLog) == audits


def test_new_batch_updates_and_audits_changed_columns(db, setup):
    run_project(db, setup["project"])
    db.commit()
    changed = [dict(r) for r in setup["rows"]]
    changed[1]["task_name"] = "Skema cuti v2"
    batch(db, setup["project"], changed)
    report = run_project(db, setup["project"])
    db.commit()
    assert report.updated["tasks"] == 1
    assert db.get(Task, "TSK-0002").task_name == "Skema cuti v2"
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "update"))
    assert (audit.entity_id, audit.before, audit.after) == (
        "TSK-0002",
        {"task_name": "Skema cuti"},
        {"task_name": "Skema cuti v2"},
    )


def test_open_manual_change_is_not_overwritten(db, setup):
    run_project(db, setup["project"])
    db.commit()
    db.get(Task, "TSK-0001").status = "blocked"
    db.add(
        TaskManualChange(
            task_id="TSK-0001", field="status", old_value="in_progress", new_value="blocked",
            source="blocker",
        )
    )  # fmt: skip
    db.commit()
    report = run_project(db, setup["project"])
    db.commit()
    assert db.get(Task, "TSK-0001").status == "blocked"
    assert report.conflicts == [
        {"task_id": "TSK-0001", "field": "status", "current": "blocked", "incoming": "in_progress"}
    ]


def test_task_id_of_other_project_is_rejected_and_left_alone(client, db, setup):
    run_project(db, setup["project"])
    db.commit()
    before = {
        "task": {c.name: getattr(db.get(Task, "TSK-0001"), c.name) for c in Task.__table__.columns},
        "deps": [(d.dependency_id, d.task_id, d.depends_on_task_id)
                 for d in db.scalars(select(TaskDependency))],
        "asgs": [(a.assignment_id, a.task_id, a.resource_id, a.assigned_date)
                 for a in db.scalars(select(Assignment))],
    }  # fmt: skip
    other = project(client, "SIMPEG", rank=2)
    # Proyek B menomori task-nya sendiri mulai TSK-0001, sama dengan kode milik proyek A.
    rows = [
        ROW | {"task_code": "TSK-0001", "task_name": "Login SIMPEG", "pic": "Sari Puspitasari",
               "estimated_days": "5", "depends_on": "TSK-0009"},
        ROW | {"task_code": "TSK-0009", "task_name": "Menu SIMPEG", "pic": ""},
    ]  # fmt: skip
    job = batch(db, other, rows)

    for _ in range(2):  # jalan kedua tetap idempoten
        report = run_project(db, other)
        db.commit()
        after_task = db.get(Task, "TSK-0001")
        assert {c.name: getattr(after_task, c.name) for c in Task.__table__.columns} == (
            before["task"]
        )
        assert [(d.dependency_id, d.task_id, d.depends_on_task_id)
                for d in db.scalars(select(TaskDependency))] == before["deps"]  # fmt: skip
        assert [(a.assignment_id, a.task_id, a.resource_id, a.assigned_date)
                for a in db.scalars(select(Assignment))] == before["asgs"]  # fmt: skip
        assert db.get(Task, "TSK-0009").project_id == other
        assert report.rejected["tasks"] == 1
        assert report.skipped_parent["task_dependencies"] == 1
        assert report.skipped_parent["assignments"] == 1
        assert report.findings["DQ-TSK-014:tolak"] == 1

    (row,) = db.scalars(
        select(RejectedRow).where(RejectedRow.job_id == job, RejectedRow.table_name == "tasks")
    )
    assert (row.row_key, row.row_number, row.rule_id, row.level) == (
        "TSK-0001", 2, "DQ-TSK-014", "tolak"
    )  # fmt: skip
    assert setup["project"] in row.message


def test_endpoint_runs_etl_and_needs_known_project(client, setup):
    response = client.post(f"{DATA}/etl/run", params={"project_id": setup["project"]})
    assert response.status_code == 200, response.text
    assert response.json()[0]["inserted"]["tasks"] == 2
    assert client.post(f"{DATA}/etl/run", params={"project_id": "PRJ-999"}).status_code == 404
