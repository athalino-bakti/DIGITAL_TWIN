"""Endpoint pengalihan task saat anggota tidak hadir (DIG-35).

Dipasang langsung di `app/api/router.py` dengan prefix /data, sehingga router modul Data
tidak perlu diubah dan PR modul Data yang berjalan paralel tidak saling bentrok.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data import takeover_service as service
from app.modules.data.enums import AVAILABILITY_ID_PATTERN, TASK_ID_PATTERN
from app.modules.data.router import to_http
from app.modules.data.service import AvailabilityNotFoundError, DataValidationError
from app.modules.data.takeover_schemas import (
    AffectedTask,
    AssignmentRead,
    ReplacementCandidate,
    TakeoverRequest,
    TakeoverResult,
)

router = APIRouter(prefix="/data", tags=["Data"])

# Riwayat penugasan, kandidat pengganti, dan task terdampak memperlihatkan beban dan
# ketidakhadiran anggota lain (DIG-19). Pengalihan task bagian dari pencatatan
# ketidakhadiran dan rotasi (FR-06).
WORKLOAD_READ = [Depends(require_permission(Perm.WORKLOAD_READ_ALL))]
TAKEOVER_WRITE = [Depends(require_permission(Perm.AVAILABILITY_WRITE))]

Db = Annotated[Session, Depends(get_db)]
TaskIdPath = Annotated[str, Path(pattern=TASK_ID_PATTERN, examples=["TSK-0001"])]
AvailabilityIdPath = Annotated[str, Path(pattern=AVAILABILITY_ID_PATTERN, examples=["AVL-001"])]
TASK_NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Task tidak ditemukan"}}


@router.get(
    "/tasks/{task_id}/assignments",
    dependencies=WORKLOAD_READ,
    response_model=list[AssignmentRead],
    responses=TASK_NOT_FOUND,
    summary="Riwayat penugasan sebuah task (D-07)",
)
def list_task_assignments(db: Db, task_id: TaskIdPath) -> list[AssignmentRead]:
    try:
        return service.list_task_assignments(db, task_id)
    except service.TaskNotFoundError as exc:
        raise to_http(exc) from exc


@router.get(
    "/tasks/{task_id}/replacement-candidates",
    dependencies=WORKLOAD_READ,
    response_model=list[ReplacementCandidate],
    responses=TASK_NOT_FOUND,
    summary="Kandidat pengganti untuk sebuah task",
)
def replacement_candidates(
    db: Db,
    task_id: TaskIdPath,
    on: Annotated[date | None, Query(description="Tanggal pengalihan, bawaan hari ini")] = None,
) -> list[ReplacementCandidate]:
    """Anggota dengan peran yang sama (utama atau rangkap) atau yang bisa lintas peran,
    yang hadir pada tanggal itu. Yang penugasan aktifnya paling sedikit tampil lebih dulu."""
    try:
        return service.replacement_candidates(db, task_id, on or date.today())
    except service.TaskNotFoundError as exc:
        raise to_http(exc) from exc


@router.post(
    "/tasks/{task_id}/takeover",
    dependencies=TAKEOVER_WRITE,
    response_model=TakeoverResult,
    responses=TASK_NOT_FOUND,
    summary="Alihkan task ke anggota lain",
)
def take_over(db: Db, task_id: TaskIdPath, payload: TakeoverRequest) -> TakeoverResult:
    """Dalam satu transaksi: penugasan lama diberi released_date = takeover_date, lalu
    penugasan baru dibuat dengan is_takeover = true dan role_in_task = peran task."""
    try:
        return service.take_over(db, task_id, payload)
    except (service.TaskNotFoundError, DataValidationError) as exc:
        raise to_http(exc) from exc


@router.get(
    "/availability/{availability_id}/affected-tasks",
    dependencies=WORKLOAD_READ,
    response_model=list[AffectedTask],
    responses={status.HTTP_404_NOT_FOUND: {"description": "Catatan tidak ditemukan"}},
    summary="Task yang terdampak oleh ketidakhadiran",
)
def affected_tasks(db: Db, availability_id: AvailabilityIdPath) -> list[AffectedTask]:
    try:
        return service.affected_tasks(db, availability_id)
    except AvailabilityNotFoundError as exc:
        raise to_http(exc) from exc
