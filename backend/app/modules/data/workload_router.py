"""Endpoint D-08 workload_items, beban non-proyek (DIG-30).

Router ini dipasang di router modul Data (`router.include_router`), sehingga path-nya ikut
berawalan /data. Dipisah dari `router.py` supaya PR modul Data yang berjalan paralel tidak
saling bentrok.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm

# Modul router Data diimpor sebagai objek modul dan `to_http` dipanggil saat request, karena
# router.py mengimpor modul ini ketika ia sendiri belum selesai dimuat.
from app.modules.data import router as data_routes
from app.modules.data import workload_service as service
from app.modules.data.enums import (
    PROJECT_ID_PATTERN,
    RESOURCE_ID_PATTERN,
    WORKLOAD_ITEM_ID_PATTERN,
    WorkloadItemType,
)
from app.modules.data.service import ConflictError, DataValidationError
from app.modules.data.workload_schemas import (
    WorkloadImportRequest,
    WorkloadImportResult,
    WorkloadItemCreate,
    WorkloadItemRead,
    WorkloadItemUpdate,
)

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
ItemIdPath = Annotated[str, Path(pattern=WORKLOAD_ITEM_ID_PATTERN, examples=["WLI-0001"])]
CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Bentrok dengan data lain"}}

# Izin D-08 (DIG-226). Daftar beban per orang hanya untuk peran yang boleh melihat beban seluruh
# anggota (DIG-19). Input dan impor oleh Administrator Data, yang di PuTI dipegang SA atau Kaur
# sebagai peran kedua, sehingga pemegangnya tetap bisa melihat daftar.
WORKLOAD_READ = [Depends(require_permission(Perm.WORKLOAD_READ_ALL))]
WORKLOAD_WRITE = [Depends(require_permission(Perm.MASTER_DATA_WRITE))]
WORKLOAD_IMPORT = [Depends(require_permission(Perm.IMPORT_RUN))]


@router.get(
    "/workload-items",
    dependencies=WORKLOAD_READ,
    response_model=list[WorkloadItemRead],
    summary="Daftar beban non-proyek (D-08)",
)
def list_workload_items(
    db: Db,
    resource_id: Annotated[str | None, Query(pattern=RESOURCE_ID_PATTERN)] = None,
    item_type: WorkloadItemType | None = None,
    related_project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    open_only: bool = False,
    received_from: date | None = None,
    received_to: date | None = None,
) -> list[WorkloadItemRead]:
    """Terbaru lebih dulu. `open_only` hanya menampilkan item yang belum selesai."""
    return service.list_workload_items(
        db, resource_id, item_type, related_project_id, open_only, received_from, received_to
    )


@router.post(
    "/workload-items",
    dependencies=WORKLOAD_WRITE,
    response_model=WorkloadItemRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Tambah item operasional atau tiket",
)
def create_workload_item(db: Db, payload: WorkloadItemCreate) -> WorkloadItemRead:
    try:
        return service.create_workload_item(db, payload)
    except (DataValidationError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc


@router.post(
    "/workload-items/import",
    dependencies=WORKLOAD_IMPORT,
    response_model=WorkloadImportResult,
    responses=CONFLICT,
    summary="Impor CSV D-08 (periksa dulu dengan dry_run)",
)
def import_workload_items(db: Db, payload: WorkloadImportRequest) -> WorkloadImportResult:
    """Seluruh berkas diperiksa lebih dulu. Bila ada satu baris salah, tidak ada yang disimpan
    dan `errors` berisi kesalahan per baris. Baris dengan item_id yang sudah ada memperbarui
    item tersebut, sehingga impor ulang tidak menggandakan data."""
    try:
        return service.import_workload_items(db, payload)
    except ConflictError as exc:
        raise data_routes.to_http(exc) from exc


@router.patch(
    "/workload-items/{item_id}",
    dependencies=WORKLOAD_WRITE,
    response_model=WorkloadItemRead,
    responses=CONFLICT,
    summary="Ubah sebagian kolom item beban non-proyek",
)
def update_workload_item(
    db: Db, item_id: ItemIdPath, payload: WorkloadItemUpdate
) -> WorkloadItemRead:
    try:
        return service.update_workload_item(db, item_id, payload)
    except (service.WorkloadItemNotFoundError, DataValidationError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc


@router.delete(
    "/workload-items/{item_id}",
    dependencies=WORKLOAD_WRITE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus item beban non-proyek",
)
def delete_workload_item(db: Db, item_id: ItemIdPath) -> Response:
    try:
        service.delete_workload_item(db, item_id)
    except (service.WorkloadItemNotFoundError, ConflictError) as exc:
        raise data_routes.to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
