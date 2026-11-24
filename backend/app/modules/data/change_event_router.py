"""Endpoint D-10 change_events, pencatatan kejadian perubahan (DIG-33, DIG-149).

Router ini dipasang di akhir router modul Data (`router.include_router`), sehingga path-nya
ikut berawalan /data. Dipisah dari `router.py` supaya PR modul Data yang berjalan paralel
tidak saling bentrok.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import Perm

# Modul router Data diimpor sebagai objek modul dan `to_http` dipanggil saat request, karena
# router.py mengimpor modul ini ketika ia sendiri belum selesai dimuat.
from app.modules.data import change_event_service as service
from app.modules.data import router as data_routes
from app.modules.data.change_event_schemas import (
    ChangeEventCreate,
    ChangeEventRead,
    ChangeEventUpdate,
)
from app.modules.data.enums import (
    EVENT_ID_PATTERN,
    PROJECT_ID_PATTERN,
    TASK_ID_PATTERN,
    ChangeEventType,
)
from app.modules.data.service import ConflictError, DataValidationError

router = APIRouter()

# Riwayat perubahan dibaca Kaur/Asman dan System Analyst; pencatatan oleh keduanya (FR-05).
# Akses anggota tim ke task miliknya sendiri menyusul di DIG-94.
EVENT_READ = [Depends(require_permission(Perm.WORKLOAD_READ_ALL))]
EVENT_WRITE = [Depends(require_permission(Perm.CHANGE_EVENT_WRITE))]
# Untuk endpoint yang perlu tahu siapa pencatatnya (jejak perubahan task, DIG-162).
EventWriter = Annotated[AppUser, Depends(require_permission(Perm.CHANGE_EVENT_WRITE))]

Db = Annotated[Session, Depends(get_db)]
EventIdPath = Annotated[str, Path(pattern=EVENT_ID_PATTERN, examples=["EVT-001"])]
CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Bentrok dengan data lain"}}
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Kejadian tidak ditemukan"}}


@router.get(
    "/change-events",
    dependencies=EVENT_READ,
    response_model=list[ChangeEventRead],
    summary="Riwayat kejadian perubahan (D-10)",
)
def list_change_events(
    db: Db,
    project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    event_type: Annotated[list[ChangeEventType] | None, Query()] = None,
    affected_task_id: Annotated[str | None, Query(pattern=TASK_ID_PATTERN)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[ChangeEventRead]:
    """Terbaru lebih dulu. Saring per proyek atau per task untuk riwayat perubahannya;
    `event_type` boleh diulang, misalnya `?event_type=change_request&event_type=priority_change`."""
    return service.list_change_events(
        db, project_id, event_type, affected_task_id, date_from, date_to
    )


@router.get(
    "/change-events/{event_id}",
    dependencies=EVENT_READ,
    response_model=ChangeEventRead,
    responses=NOT_FOUND,
    summary="Detail kejadian perubahan",
)
def get_change_event(db: Db, event_id: EventIdPath) -> ChangeEventRead:
    try:
        return service.read_change_event(db, event_id)
    except service.ChangeEventNotFoundError as exc:
        raise data_routes.to_http(exc) from exc


@router.post(
    "/change-events",
    response_model=ChangeEventRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Catat CR, perubahan prioritas, blocker, overrun, atau hotfix",
)
def create_change_event(db: Db, user: EventWriter, payload: ChangeEventCreate) -> ChangeEventRead:
    try:
        return service.create_change_event(db, payload, user.user_id)
    except (DataValidationError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc


@router.patch(
    "/change-events/{event_id}",
    dependencies=EVENT_WRITE,
    response_model=ChangeEventRead,
    responses=CONFLICT | NOT_FOUND,
    summary="Ubah sebagian kolom kejadian perubahan",
)
def update_change_event(
    db: Db, event_id: EventIdPath, payload: ChangeEventUpdate
) -> ChangeEventRead:
    try:
        return service.update_change_event(db, event_id, payload)
    except (service.ChangeEventNotFoundError, DataValidationError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc


@router.delete(
    "/change-events/{event_id}",
    dependencies=EVENT_WRITE,
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
    summary="Hapus kejadian perubahan",
)
def delete_change_event(db: Db, event_id: EventIdPath) -> Response:
    try:
        service.delete_change_event(db, event_id)
    except (service.ChangeEventNotFoundError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
