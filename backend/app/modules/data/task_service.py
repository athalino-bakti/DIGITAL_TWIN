"""Daftar task dan pembaruan status task secara manual (DIG-36, DIG-161).

Status proyek dan `actual_launch_date` sudah bisa diubah lewat PATCH /data/projects (DIG-20).

Aturan status di bawah dicek terhadap 1.200 task di dataset dosbim (`puti_datasets.xlsx`)
dan tidak ada satu baris pun yang dilanggar:

| status | actual_start | actual_finish |
| --- | --- | --- |
| not_started | kosong | kosong |
| in_progress, blocked, in_qa | wajib | kosong |
| on_hold, dropped | boleh | kosong |
| done | wajib | wajib |

`dod_fulfilled = true` hanya untuk task berstatus done (di dataset dosbim 500 dari 527 task
done memenuhi DoD, dan tidak ada task lain yang memenuhinya). `actual_start` boleh lebih awal
dari `planned_start` (296 task di dataset dosbim).
"""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.enums import TaskStatus
from app.modules.data.models import Project, Task
from app.modules.data.service import (
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
)
from app.modules.data.task_schemas import TaskRead, TaskStatusUpdate


class TaskNotFoundError(NotFoundError):
    label = "Task"


STATUS_LABEL = {
    TaskStatus.NOT_STARTED: "belum dimulai",
    TaskStatus.IN_PROGRESS: "sedang dikerjakan",
    TaskStatus.BLOCKED: "terhambat",
    TaskStatus.ON_HOLD: "ditunda",
    TaskStatus.IN_QA: "dalam QA",
    TaskStatus.DONE: "selesai",
    TaskStatus.DROPPED: "dibatalkan",
}
NEEDS_START = frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.IN_QA})
NOT_NULL = frozenset({"status", "dod_fulfilled"})


def check_task_status_rules(values: Mapping[str, Any]) -> list[FieldError]:
    """Aturan status, tanggal aktual, dan DoD untuk satu task tanpa menyentuh basis data."""
    status = TaskStatus(values["status"])
    start = values.get("actual_start")
    finish = values.get("actual_finish")
    label = STATUS_LABEL[status]
    errors: list[FieldError] = []

    if status == TaskStatus.NOT_STARTED and start is not None:
        errors.append(
            FieldError("actual_start", f"Harus kosong untuk task {label}", "start_not_allowed")
        )
    if (status in NEEDS_START or status == TaskStatus.DONE) and start is None:
        errors.append(
            FieldError("actual_start", f"Wajib diisi untuk task {label}", "start_required")
        )
    if status == TaskStatus.DONE:
        if finish is None:
            errors.append(
                FieldError("actual_finish", "Wajib diisi untuk task selesai", "finish_required")
            )
    elif finish is not None:
        errors.append(
            FieldError(
                "actual_finish",
                f"Harus kosong selama task belum selesai ({label})",
                "finish_not_allowed",
            )
        )
    if start is not None and finish is not None and finish < start:
        errors.append(
            FieldError(
                "actual_finish", "Tidak boleh lebih awal dari tanggal mulai aktual", "date_order"
            )
        )
    if values.get("dod_fulfilled") and status != TaskStatus.DONE:
        errors.append(
            FieldError(
                "dod_fulfilled",
                "Definition of Done hanya bisa terpenuhi untuk task selesai",
                "dod_not_done",
            )
        )
    return errors


def to_read(task: Task, project_name: str) -> TaskRead:
    return TaskRead(
        task_id=task.task_id,
        project_id=task.project_id,
        project_name=project_name,
        feature_name=task.feature_name,
        task_name=task.task_name,
        required_role_id=task.required_role_id,
        complexity_id=task.complexity_id,
        priority_rank=task.priority_rank,
        estimated_days=task.estimated_days,
        phase=task.phase,
        planned_start=task.planned_start,
        planned_finish=task.planned_finish,
        actual_start=task.actual_start,
        actual_finish=task.actual_finish,
        status=task.status,
        qa_reject_count=task.qa_reject_count,
        dod_fulfilled=task.dod_fulfilled,
    )


def _query():
    return select(Task, Project.project_name).join(Project, Project.project_id == Task.project_id)


def list_tasks(
    db: Session,
    project_id: str | None = None,
    status: list[TaskStatus] | None = None,
    required_role_id: str | None = None,
) -> list[TaskRead]:
    """Urut per proyek, lalu prioritas (1 lebih dulu), lalu jadwal rencana."""
    query = _query().order_by(Task.project_id, Task.priority_rank, Task.planned_start, Task.task_id)
    if project_id is not None:
        query = query.where(Task.project_id == project_id)
    if status:
        query = query.where(Task.status.in_(status))
    if required_role_id is not None:
        query = query.where(Task.required_role_id == required_role_id)
    return [to_read(task, name) for task, name in db.execute(query)]


def get_task(db: Session, task_id: str) -> TaskRead:
    row = db.execute(_query().where(Task.task_id == task_id)).first()
    if row is None:
        raise TaskNotFoundError(task_id)
    return to_read(*row)


def update_task_status(db: Session, task_id: str, payload: TaskStatusUpdate) -> TaskRead:
    task = db.get(Task, task_id)
    if task is None:
        raise TaskNotFoundError(task_id)
    changes = payload.model_dump(exclude_unset=True)
    errors = [
        FieldError(field, "Kolom ini wajib diisi", "missing")
        for field, value in changes.items()
        if value is None and field in NOT_NULL
    ]
    if errors:
        raise DataValidationError(errors)
    current = {
        "status": task.status,
        "actual_start": task.actual_start,
        "actual_finish": task.actual_finish,
        "dod_fulfilled": task.dod_fulfilled,
    }
    errors = check_task_status_rules(current | changes)
    if errors:
        raise DataValidationError(errors)
    for field, value in changes.items():
        setattr(task, field, value)
    commit(db)
    return get_task(db, task_id)
