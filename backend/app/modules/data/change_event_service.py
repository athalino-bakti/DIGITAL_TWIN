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

from app.modules.data.change_event_detail_rules import check_event_date_change
from app.modules.data.change_event_schemas import (
    ChangeEventCreate,
    ChangeEventRead,
    ChangeEventUpdate,
    TaskEffect,
)
from app.modules.data.enums import ChangeEventType, Decision, ResolutionMode, TaskStatus
from app.modules.data.models import ChangeEvent, Project, Task
from app.modules.data.service import (
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
    ensure_id_free,
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


EFFECT_MODES = frozenset({ResolutionMode.SWAP_TASK, ResolutionMode.RESHUFFLE})
CLOSED_TASK_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.DROPPED})


def check_task_effect_rules(
    values: Mapping[str, Any], effect: TaskEffect, task_status: TaskStatus | None
) -> list[FieldError]:
    """Kapan efek samping ke task boleh dipakai (DIG-150), tanpa menyentuh basis data.

    `task_status` = status task terdampak saat ini, atau None bila task tidak ada.
    """
    errors: list[FieldError] = []
    if effect.status is None and effect.priority_rank is None:
        errors.append(
            FieldError("task_effect", "Isi status atau prioritas baru task", "effect_empty")
        )
    if values.get("affected_task_id") is None:
        errors.append(
            FieldError("affected_task_id", "Pilih task yang terdampak", "effect_needs_task")
        )
    if values.get("decision") != Decision.ACCEPT_NOW:
        errors.append(
            FieldError(
                "decision",
                "Task hanya berubah bila perubahan diterima sekarang",
                "effect_needs_accept",
            )
        )
    if values.get("resolution_mode") not in EFFECT_MODES:
        errors.append(
            FieldError(
                "resolution_mode",
                "Task hanya berubah pada mode tukar task atau atur ulang prioritas",
                "effect_needs_mode",
            )
        )
    if effect.status is not None and task_status in CLOSED_TASK_STATUSES:
        state = "selesai" if task_status == TaskStatus.DONE else "dibatalkan"
        errors.append(
            FieldError(
                "task_effect.status",
                f"Task sudah {state}, statusnya tidak bisa diubah",
                "task_closed",
            )
        )
    return errors


def to_read(
    event: ChangeEvent,
    project_name: str,
    task_name: str | None,
    task_status: TaskStatus | None = None,
    task_priority: int | None = None,
) -> ChangeEventRead:
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
        affected_task_status=task_status,
        affected_task_priority_rank=task_priority,
        extension_days=event.extension_days,
    )


def _query():
    return (
        select(ChangeEvent, Project.project_name, Task.task_name, Task.status, Task.priority_rank)
        .join(Project, Project.project_id == ChangeEvent.project_id)
        .outerjoin(Task, Task.task_id == ChangeEvent.affected_task_id)
    )


def _read_one(db: Session, event_id: str) -> ChangeEventRead:
    row = db.execute(_query().where(ChangeEvent.event_id == event_id)).one()
    return to_read(*row)


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
    return [to_read(*row) for row in db.execute(query)]


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
    effect = payload.task_effect
    values = payload.model_dump(exclude={"task_effect"})
    validate_event(db, values)
    task = None
    if effect is not None:
        if values["affected_task_id"] is not None:
            # Dikunci sampai commit supaya dua kejadian tidak mengubah task yang sama bersamaan.
            task = db.get(Task, values["affected_task_id"], with_for_update=True)
        errors = check_task_effect_rules(values, effect, task.status if task else None)
        if errors:
            raise DataValidationError(errors)
    if values["event_id"] is None:
        values["event_id"] = next_event_id(db)
    else:
        # Menolak juga nomor yang sama dengan padding berbeda, misalnya EVT-0001 vs EVT-001.
        ensure_id_free(db, ChangeEvent.event_id, values["event_id"], "event_id", "kejadian")
    db.add(ChangeEvent(**values))
    if task is not None and effect is not None:
        # Kejadian dan perubahan task tersimpan bersama, atau tidak sama sekali.
        if effect.status is not None:
            task.status = TaskStatus(effect.status)
        if effect.priority_rank is not None:
            task.priority_rank = effect.priority_rank
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
    if "event_date" in changes:
        # Detail kejadian (persetujuan, tanggal selesai) tidak boleh jadi lebih awal dari
        # tanggal kejadian yang baru (DATA_CONTRACT 7.3).
        errors = check_event_date_change(db, event_id, values["event_date"])
        if errors:
            raise DataValidationError(errors)
    for field, value in changes.items():
        setattr(event, field, value)
    commit(db)
    return _read_one(db, event_id)


def delete_change_event(db: Session, event_id: str) -> None:
    db.delete(get_change_event(db, event_id))
    commit(db)
