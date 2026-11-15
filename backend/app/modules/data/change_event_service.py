"""Layanan D-10 change_events, pencatatan kejadian perubahan (DIG-33, DIG-149).

Aturan isi di bawah dicek terhadap 360 baris `change_events` di dataset dosbim
(`puti_datasets.xlsx`) dan tidak ada satu baris pun yang dilanggar:

- `affected_task_id` harus task milik `project_id` yang sama.
- `extension_days` > 0 hanya untuk `resolution_mode = extend_duration`, dan pada mode itu
  wajib diisi. Mode lain memakai 0 atau kosong (DATA_CONTRACT bagian 5).
- `resolution_mode` hanya diisi bersama `decision`.
- `event_date` tidak sebelum `start_date` proyek.

Kombinasi `event_type`, `decision`, dan `resolution_mode` sengaja tidak dibatasi. Di dataset
dosbim setiap kombinasi muncul, termasuk `reject` dengan mode resolusi dan blocker yang
punya keputusan, jadi pembatasan di sini akan menolak data baseline (pelajaran dari aturan
hotfix D-08, DIG-30).
"""

from collections.abc import Mapping
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.data.change_event_schemas import (
    ChangeEventCreate,
    ChangeEventRead,
    ChangeEventUpdate,
)
from app.modules.data.enums import ChangeEventType, ResolutionMode
from app.modules.data.models import ChangeEvent, Project, Task
from app.modules.data.service import (
    ConflictError,
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
    next_id,
)


class ChangeEventNotFoundError(NotFoundError):
    label = "Kejadian perubahan"


NOT_NULL = frozenset({"project_id", "event_type", "event_date"})


def check_change_event_rules(
    values: Mapping[str, Any],
    project_start: date | None,
    task_project: str | None,
) -> list[FieldError]:
    """Aturan isi satu kejadian tanpa menyentuh basis data.

    `project_start` = `start_date` proyek, atau None bila proyek tidak terdaftar.
    `task_project` = proyek pemilik `affected_task_id`, atau None bila task tidak terdaftar.
    """
    errors: list[FieldError] = []
    project = values["project_id"]
    if project_start is None:
        errors.append(
            FieldError("project_id", f"Proyek {project} tidak terdaftar", "project_not_found")
        )
    elif values["event_date"] < project_start:
        errors.append(
            FieldError(
                "event_date",
                f"Tidak boleh sebelum proyek dimulai ({project_start.isoformat()})",
                "before_project_start",
            )
        )

    task = values.get("affected_task_id")
    if task is not None:
        if task_project is None:
            errors.append(
                FieldError("affected_task_id", f"Task {task} tidak terdaftar", "task_not_found")
            )
        elif task_project != project and project_start is not None:
            errors.append(
                FieldError(
                    "affected_task_id",
                    f"Task {task} milik proyek {task_project}, bukan {project}",
                    "task_other_project",
                )
            )

    mode = values.get("resolution_mode")
    if mode is not None and values.get("decision") is None:
        errors.append(
            FieldError("decision", "Isi keputusan bila mode resolusi diisi", "mode_needs_decision")
        )
    days = values.get("extension_days")
    if mode == ResolutionMode.EXTEND_DURATION:
        if days is None or days <= 0:
            errors.append(
                FieldError(
                    "extension_days",
                    "Isi tambahan hari (lebih dari 0) untuk perpanjangan durasi",
                    "extension_required",
                )
            )
    elif days:
        errors.append(
            FieldError(
                "extension_days",
                "Tambahan hari hanya untuk mode resolusi perpanjangan durasi",
                "extension_without_extend",
            )
        )
    return errors


def validate_event(db: Session, values: Mapping[str, Any]) -> None:
    project_start = db.scalar(
        select(Project.start_date).where(Project.project_id == values["project_id"])
    )
    task_project = None
    if values.get("affected_task_id") is not None:
        task_project = db.scalar(
            select(Task.project_id).where(Task.task_id == values["affected_task_id"])
        )
    errors = check_change_event_rules(values, project_start, task_project)
    if errors:
        raise DataValidationError(errors)


def to_read(event: ChangeEvent, project_name: str, task_name: str | None) -> ChangeEventRead:
    return ChangeEventRead(
        event_id=event.event_id,
        project_id=event.project_id,
        project_name=project_name,
        event_type=event.event_type,
        event_date=event.event_date,
        requested_by=event.requested_by,
        decision=event.decision,
        resolution_mode=event.resolution_mode,
        affected_task_id=event.affected_task_id,
        affected_task_name=task_name,
        extension_days=event.extension_days,
    )


def _query():
    return (
        select(ChangeEvent, Project.project_name, Task.task_name)
        .join(Project, Project.project_id == ChangeEvent.project_id)
        .outerjoin(Task, Task.task_id == ChangeEvent.affected_task_id)
    )


def _read_one(db: Session, event_id: str) -> ChangeEventRead:
    event, project_name, task_name = db.execute(
        _query().where(ChangeEvent.event_id == event_id)
    ).one()
    return to_read(event, project_name, task_name)


def list_change_events(
    db: Session,
    project_id: str | None = None,
    event_type: list[ChangeEventType] | None = None,
    affected_task_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ChangeEventRead]:
    """Terbaru lebih dulu, sebagai riwayat perubahan per proyek atau per task."""
    query = _query().order_by(ChangeEvent.event_date.desc(), ChangeEvent.event_id.desc())
    if project_id is not None:
        query = query.where(ChangeEvent.project_id == project_id)
    if event_type:
        query = query.where(ChangeEvent.event_type.in_(event_type))
    if affected_task_id is not None:
        query = query.where(ChangeEvent.affected_task_id == affected_task_id)
    if date_from is not None:
        query = query.where(ChangeEvent.event_date >= date_from)
    if date_to is not None:
        query = query.where(ChangeEvent.event_date <= date_to)
    return [to_read(event, project, task) for event, project, task in db.execute(query)]


def get_change_event(db: Session, event_id: str) -> ChangeEvent:
    event = db.get(ChangeEvent, event_id)
    if event is None:
        raise ChangeEventNotFoundError(event_id)
    return event


def read_change_event(db: Session, event_id: str) -> ChangeEventRead:
    get_change_event(db, event_id)
    return _read_one(db, event_id)


def next_event_id(db: Session) -> str:
    return next_id(list(db.scalars(select(ChangeEvent.event_id))), "EVT")


def create_change_event(db: Session, payload: ChangeEventCreate) -> ChangeEventRead:
    values = payload.model_dump()
    validate_event(db, values)
    if values["event_id"] is None:
        values["event_id"] = next_event_id(db)
    elif db.get(ChangeEvent, values["event_id"]) is not None:
        raise ConflictError(
            f"ID {values['event_id']} sudah dipakai kejadian lain", field="event_id"
        )
    db.add(ChangeEvent(**values))
    commit(db)
    return _read_one(db, values["event_id"])


def update_change_event(db: Session, event_id: str, payload: ChangeEventUpdate) -> ChangeEventRead:
    event = get_change_event(db, event_id)
    changes = payload.model_dump(exclude_unset=True)
    errors = [
        FieldError(field, "Kolom ini wajib diisi", "missing")
        for field, value in changes.items()
        if value is None and field in NOT_NULL
    ]
    if errors:
        raise DataValidationError(errors)
    values = {c.key: getattr(event, c.key) for c in ChangeEvent.__table__.columns} | changes
    validate_event(db, values)
    for field, value in changes.items():
        setattr(event, field, value)
    commit(db)
    return _read_one(db, event_id)


def delete_change_event(db: Session, event_id: str) -> None:
    db.delete(get_change_event(db, event_id))
    commit(db)
