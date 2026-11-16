"""Endpoint "task saya": blocker dan overrun oleh pelaksana task (DIG-34, DIG-153, DIG-154).

Dipasang di akhir router modul Data, sehingga path-nya berawalan /data. Pencatatan oleh Kaur,
Asisten Manajer, dan System Analyst untuk task siapa pun tetap lewat /data/change-events.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import Perm

# `to_http` dipanggil saat request karena router.py mengimpor modul ini ketika ia sendiri
# belum selesai dimuat (sama seperti change_event_router).
from app.modules.data import my_task_service as service
from app.modules.data import router as data_routes
from app.modules.data.enums import EVENT_ID_PATTERN, TASK_ID_PATTERN
from app.modules.data.my_task_schemas import (
    MyTaskEventCreate,
    MyTaskEventResolve,
    MyTaskEventResult,
    MyTasks,
    OverrunDetection,
)
from app.modules.data.service import ConflictError, DataValidationError, NotFoundError

DETECTION_OFF = (
    "Deteksi overrun otomatis belum diaktifkan (OVERRUN_DETECTION_ENABLED). "
    "Pakai dry_run=true untuk melihat jumlah kejadian yang akan dibuat."
)


def detection_enabled() -> bool:
    return get_settings().overrun_detection_enabled


router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
OwnReader = Annotated[AppUser, Depends(require_permission(Perm.WORKLOAD_READ_OWN))]
OwnWriter = Annotated[AppUser, Depends(require_permission(Perm.CHANGE_EVENT_WRITE_OWN))]
EVENT_WRITE = [Depends(require_permission(Perm.CHANGE_EVENT_WRITE))]
TaskIdPath = Annotated[str, Path(pattern=TASK_ID_PATTERN, examples=["TSK-0001"])]
EventIdPath = Annotated[str, Path(pattern=EVENT_ID_PATTERN, examples=["EVT-001"])]
RESPONSES = {
    status.HTTP_403_FORBIDDEN: {"description": "Task tidak sedang ditugaskan kepada Anda"},
    status.HTTP_404_NOT_FOUND: {"description": "Task atau kejadian tidak ditemukan"},
    status.HTTP_409_CONFLICT: {"description": "Task sudah ditutup atau kejadian sudah ada"},
}


def to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NotTaskOwnerError):
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=exc.message)
    return data_routes.to_http(exc)


HANDLED = (service.NotTaskOwnerError, NotFoundError, DataValidationError, ConflictError)


@router.get(
    "/my-tasks",
    response_model=MyTasks,
    summary="Task yang sedang ditugaskan kepada saya dan belum selesai",
)
def list_my_tasks(db: Db, user: OwnReader) -> MyTasks:
    """Kosong (dengan `resource_id` null) bila akun belum dihubungkan ke data anggota tim."""
    return service.list_my_tasks(db, user, date.today())


@router.post(
    "/my-tasks/{task_id}/events",
    response_model=MyTaskEventResult,
    status_code=status.HTTP_201_CREATED,
    responses=RESPONSES,
    summary="Tandai task saya terhambat (blocker) atau melewati rencana (overrun)",
)
def record_event(
    db: Db, user: OwnWriter, task_id: TaskIdPath, payload: MyTaskEventCreate
) -> MyTaskEventResult:
    """Blocker mengubah task yang sedang dikerjakan (in_progress, in_qa) menjadi blocked dalam
    transaksi yang sama. Task yang belum dimulai atau sedang ditunda tetap pada statusnya."""
    try:
        return service.record_event(db, user, task_id, payload, date.today())
    except HANDLED as exc:
        raise to_http(exc) from exc


@router.post(
    "/my-tasks/{task_id}/events/{event_id}/resolve",
    response_model=MyTaskEventResult,
    responses=RESPONSES,
    summary="Tandai blocker atau overrun pada task saya sudah selesai",
)
def resolve_event(
    db: Db,
    user: OwnWriter,
    task_id: TaskIdPath,
    event_id: EventIdPath,
    payload: MyTaskEventResolve,
) -> MyTaskEventResult:
    """Mengisi `resolved_date` di `change_event_details`. Bila blocker terakhir pada task itu
    selesai, task kembali berstatus in_progress."""
    try:
        return service.resolve_event(db, user, task_id, event_id, payload, date.today())
    except HANDLED as exc:
        raise to_http(exc) from exc


@router.post(
    "/overrun-detection",
    dependencies=EVENT_WRITE,
    response_model=OverrunDetection,
    responses={status.HTTP_409_CONFLICT: {"description": "Deteksi otomatis belum diaktifkan"}},
    summary="Buat kejadian overrun untuk task yang lewat rencana dan belum punya",
)
def detect_overruns(
    db: Db,
    dry_run: Annotated[
        bool, Query(description="Hanya menghitung, tidak menyimpan apa pun")
    ] = False,
) -> OverrunDetection:
    """Tanpa `dry_run` hanya jalan bila OVERRUN_DETECTION_ENABLED=true; selain itu 409.

    Aman dijalankan berulang. Jalankan dengan `dry_run=true` dulu pada data lama untuk
    melihat berapa kejadian yang akan dibuat. Perintah yang sama tersedia untuk scheduler:
    `python -m app.modules.data.detect_overruns`."""
    if not dry_run and not detection_enabled():
        raise HTTPException(status.HTTP_409_CONFLICT, detail=DETECTION_OFF)
    return service.detect_overruns(db, date.today(), dry_run)
