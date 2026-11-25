"""Endpoint D-05 tasks: daftar dan pembaruan status task (DIG-36, DIG-161).

Dipasang langsung di `app/api/router.py` dengan prefix /data, sehingga router modul Data
tidak perlu diubah dan PR modul Data yang berjalan paralel tidak saling bentrok.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import require_permission
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import Perm
from app.modules.data import task_service as service
from app.modules.data.enums import PROJECT_ID_PATTERN, ROLE_ID_PATTERN, TASK_ID_PATTERN, TaskStatus
from app.modules.data.router import to_http
from app.modules.data.service import DataValidationError
from app.modules.data.task_schemas import TaskRead, TaskStatusUpdate

router = APIRouter(prefix="/data", tags=["Data"])

# Daftar task dibaca semua peran yang melihat master data, tetapi Anggota Tim hanya melihat
# task miliknya (DIG-94). Status task diperbarui pengelola master data; di PuTI peran ini
# dipegang System Analyst sebagai peran kedua (DIG-36).
TASK_STATUS_WRITE = [Depends(require_permission(Perm.MASTER_DATA_WRITE))]
# Pemegang salah satu izin ini melihat semua task; selainnya hanya task yang ditugaskan
# kepadanya. Administrator Data tetap melihat semua karena mengelola master data dan impor.
SEE_ALL_TASKS = {Perm.WORKLOAD_READ_ALL, Perm.MASTER_DATA_WRITE}

Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[AppUser, Depends(require_permission(Perm.MASTER_DATA_READ))]
TaskIdPath = Annotated[str, Path(pattern=TASK_ID_PATTERN, examples=["TSK-0001"])]
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Task tidak ditemukan"}}


def only_own(db: Session, user: AppUser) -> bool:
    """True bila pengguna hanya boleh melihat task miliknya sendiri (DIG-94)."""
    return not SEE_ALL_TASKS & auth_service.get_user_permissions(db, user.user_id)


@router.get(
    "/tasks",
    response_model=list[TaskRead],
    summary="Daftar task (D-05)",
)
def list_tasks(
    db: Db,
    user: Reader,
    project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    status_filter: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    required_role_id: Annotated[str | None, Query(pattern=ROLE_ID_PATTERN)] = None,
) -> list[TaskRead]:
    """Urut per proyek, lalu prioritas, lalu jadwal rencana. `status` boleh diulang.

    Tanpa `workload:read_all` atau `master_data:write` (Anggota Tim), hanya task yang pernah
    atau sedang ditugaskan ke anggota yang tertaut ke akun ini."""
    return service.list_tasks(
        db,
        project_id,
        status_filter,
        required_role_id,
        own=only_own(db, user),
        resource_id=user.resource_id,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskRead,
    responses=NOT_FOUND,
    summary="Detail task",
)
def get_task(db: Db, user: Reader, task_id: TaskIdPath) -> TaskRead:
    """Bagi Anggota Tim, task milik anggota lain dilaporkan tidak ditemukan (DIG-94)."""
    try:
        return service.get_task(db, task_id, own=only_own(db, user), resource_id=user.resource_id)
    except service.TaskNotFoundError as exc:
        raise to_http(exc) from exc


@router.patch(
    "/tasks/{task_id}/status",
    dependencies=TASK_STATUS_WRITE,
    response_model=TaskRead,
    responses=NOT_FOUND,
    summary="Ubah status, tanggal aktual, atau DoD task",
)
def update_task_status(db: Db, task_id: TaskIdPath, payload: TaskStatusUpdate) -> TaskRead:
    """Aturan dicek pada gabungan nilai lama dan baru: misalnya status done wajib punya
    actual_start dan actual_finish, dan selain done actual_finish harus kosong."""
    try:
        return service.update_task_status(db, task_id, payload)
    except (service.TaskNotFoundError, DataValidationError) as exc:
        raise to_http(exc) from exc
