from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data import service
from app.modules.data.enums import (
    AVAILABILITY_ID_PATTERN,
    COMPLEXITY_ID_PATTERN,
    PROJECT_ID_PATTERN,
    RESOURCE_ID_PATTERN,
    ROLE_ID_PATTERN,
    ProjectStatus,
)
from app.modules.data.schemas import (
    AvailabilityCreate,
    AvailabilityRead,
    AvailabilityUpdate,
    ComplexityRead,
    ComplexityUpdate,
    HolidayCreate,
    HolidayRead,
    HolidayUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
    ResourceCreate,
    ResourceRead,
    ResourceUpdate,
    RoleRead,
    RoleUpdate,
)

router = APIRouter(prefix="/data", tags=["Data"])

# D-08 beban non-proyek (DIG-30) ada di modul terpisah.
from app.modules.data.workload_router import router as workload_router  # noqa: E402

router.include_router(workload_router)

# Event log untuk process mining (DIG-37) juga di modul terpisah.
from app.modules.data.event_log_router import router as event_log_router  # noqa: E402

router.include_router(event_log_router)

# Unggah Project Plan CSV/XLSX ke staging (DIG-25) juga di modul terpisah.
from app.modules.data.project_plan_router import router as project_plan_router  # noqa: E402

router.include_router(project_plan_router)

# Laporan kualitas data dan baris ditolak per impor (DIG-146) juga di modul terpisah.
from app.modules.data.quality_router import router as quality_router  # noqa: E402

router.include_router(quality_router)

Db = Annotated[Session, Depends(get_db)]
ProjectIdPath = Annotated[str, Path(pattern=PROJECT_ID_PATTERN, examples=["PRJ-001"])]
ComplexityIdPath = Annotated[str, Path(pattern=COMPLEXITY_ID_PATTERN, examples=["CX-M"])]
ResourceIdPath = Annotated[str, Path(pattern=RESOURCE_ID_PATTERN, examples=["RES-001"])]
RoleIdPath = Annotated[str, Path(pattern=ROLE_ID_PATTERN, examples=["ROLE-BE"])]
AvailabilityIdPath = Annotated[str, Path(pattern=AVAILABILITY_ID_PATTERN, examples=["AVL-001"])]
# Tanggal di path tetap string YYYY-MM-DD, sama seperti body (DATA_CONTRACT.md bagian 5).
HolidayDatePath = Annotated[str, Path(pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2026-12-25"])]
ResourceIdQuery = Annotated[str | None, Query(pattern=RESOURCE_ID_PATTERN)]

CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Bentrok dengan data lain"}}
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Proyek tidak ditemukan"}}

# Izin per kelompok endpoint (DIG-226). Tanpa token: 401, tanpa izin: 403.
# Ketidakhadiran (D-09) hanya untuk peran yang boleh melihat beban seluruh anggota (DIG-19),
# dan dicatat oleh Kaur/Asman atau System Analyst (FR-06).
MASTER_READ = [Depends(require_permission(Perm.MASTER_DATA_READ))]
MASTER_WRITE = [Depends(require_permission(Perm.MASTER_DATA_WRITE))]
AVAILABILITY_READ = [Depends(require_permission(Perm.WORKLOAD_READ_ALL))]
AVAILABILITY_WRITE = [Depends(require_permission(Perm.AVAILABILITY_WRITE))]


def to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{exc.label} tidak ditemukan")
    if isinstance(exc, service.DataValidationError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[error.as_detail() for error in exc.errors],
        )
    if isinstance(exc, service.ConflictError):
        detail: dict = {"msg": exc.message}
        if exc.field:
            detail["loc"] = ["body", exc.field]
        return HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    raise exc


@router.get(
    "/projects",
    dependencies=MASTER_READ,
    response_model=list[ProjectRead],
    summary="Daftar proyek (D-01)",
)
def list_projects(
    db: Db,
    status_filter: Annotated[list[ProjectStatus] | None, Query(alias="status")] = None,
    active_only: bool = False,
) -> list[ProjectRead]:
    """Urut dari prioritas tertinggi (`priority_rank` 1)."""
    return service.list_projects(db, status=status_filter, active_only=active_only)


@router.post(
    "/projects",
    dependencies=MASTER_WRITE,
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Tambah proyek",
)
def create_project(db: Db, payload: ProjectCreate) -> ProjectRead:
    try:
        return service.create_project(db, payload)
    except (service.DataValidationError, service.ConflictError) as exc:
        raise to_http(exc) from exc


@router.get(
    "/projects/{project_id}",
    dependencies=MASTER_READ,
    response_model=ProjectRead,
    responses=NOT_FOUND,
    summary="Detail",
)
def get_project(db: Db, project_id: ProjectIdPath) -> ProjectRead:
    try:
        return service.to_read(service.get_project(db, project_id))
    except service.ProjectNotFoundError as exc:
        raise to_http(exc) from exc


@router.patch(
    "/projects/{project_id}",
    dependencies=MASTER_WRITE,
    response_model=ProjectRead,
    responses=NOT_FOUND | CONFLICT,
    summary="Ubah sebagian kolom proyek",
)
def update_project(db: Db, project_id: ProjectIdPath, payload: ProjectUpdate) -> ProjectRead:
    try:
        return service.update_project(db, project_id, payload)
    except (
        service.ProjectNotFoundError,
        service.DataValidationError,
        service.ConflictError,
    ) as exc:
        raise to_http(exc) from exc


@router.delete(
    "/projects/{project_id}",
    dependencies=MASTER_WRITE,
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
    summary="Hapus proyek yang belum dipakai data lain",
)
def delete_project(db: Db, project_id: ProjectIdPath) -> Response:
    try:
        service.delete_project(db, project_id)
    except (service.ProjectNotFoundError, service.ConflictError) as exc:
        raise to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/complexity-levels",
    dependencies=MASTER_READ,
    response_model=list[ComplexityRead],
    summary="Daftar level kompleksitas (D-04)",
)
def list_complexity_levels(db: Db) -> list[ComplexityRead]:
    """Urut dari level tersulit, beserta jumlah task yang memakai tiap level."""
    return service.list_complexity_levels(db)


@router.patch(
    "/complexity-levels/{complexity_id}",
    dependencies=MASTER_WRITE,
    response_model=ComplexityRead,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Level tidak ditemukan"}},
    summary="Ubah rentang hari dan bobot level kompleksitas",
)
def update_complexity_level(
    db: Db, complexity_id: ComplexityIdPath, payload: ComplexityUpdate
) -> ComplexityRead:
    try:
        return service.update_complexity_level(db, complexity_id, payload)
    except (
        service.ComplexityNotFoundError,
        service.DataValidationError,
        service.ConflictError,
    ) as exc:
        raise to_http(exc) from exc


@router.get(
    "/resources",
    dependencies=MASTER_READ,
    response_model=list[ResourceRead],
    summary="Daftar anggota (D-02)",
)
def list_resources(db: Db) -> list[ResourceRead]:
    return service.list_resources(db)


@router.post(
    "/resources",
    dependencies=MASTER_WRITE,
    response_model=ResourceRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Tambah anggota",
)
def create_resource(db: Db, payload: ResourceCreate) -> ResourceRead:
    try:
        return service.create_resource(db, payload)
    except (service.DataValidationError, service.ConflictError) as exc:
        raise to_http(exc) from exc


@router.get(
    "/resources/{resource_id}",
    dependencies=MASTER_READ,
    response_model=ResourceRead,
    summary="Detail anggota",
)
def get_resource(db: Db, resource_id: ResourceIdPath) -> ResourceRead:
    try:
        return service.resource_read(service.get_resource(db, resource_id))
    except service.ResourceNotFoundError as exc:
        raise to_http(exc) from exc


@router.patch(
    "/resources/{resource_id}",
    dependencies=MASTER_WRITE,
    response_model=ResourceRead,
    responses=CONFLICT,
    summary="Ubah sebagian kolom anggota",
)
def update_resource(db: Db, resource_id: ResourceIdPath, payload: ResourceUpdate) -> ResourceRead:
    try:
        return service.update_resource(db, resource_id, payload)
    except (
        service.ResourceNotFoundError,
        service.DataValidationError,
        service.ConflictError,
    ) as exc:
        raise to_http(exc) from exc


@router.delete(
    "/resources/{resource_id}",
    dependencies=MASTER_WRITE,
    status_code=status.HTTP_204_NO_CONTENT,
    responses=CONFLICT,
    summary="Hapus anggota yang belum dipakai data lain",
)
def delete_resource(db: Db, resource_id: ResourceIdPath) -> Response:
    try:
        service.delete_resource(db, resource_id)
    except (service.ResourceNotFoundError, service.ConflictError) as exc:
        raise to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/roles", dependencies=MASTER_READ, response_model=list[RoleRead], summary="Daftar peran (D-03)"
)
def list_roles(db: Db) -> list[RoleRead]:
    return service.list_roles(db)


@router.patch(
    "/roles/{role_id}",
    dependencies=MASTER_WRITE,
    response_model=RoleRead,
    summary="Ubah kapasitas acuan dan deskripsi peran",
)
def update_role(db: Db, role_id: RoleIdPath, payload: RoleUpdate) -> RoleRead:
    try:
        return service.update_role(db, role_id, payload)
    except (service.RoleNotFoundError, service.DataValidationError, service.ConflictError) as exc:
        raise to_http(exc) from exc


# --- D-09 availability dan D-11 holidays (DIG-23) ---


def parse_path_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[{"loc": ["path", "holiday_date"], "msg": "Tanggal tidak valid"}],
        ) from exc


@router.get(
    "/availability",
    dependencies=AVAILABILITY_READ,
    response_model=list[AvailabilityRead],
    summary="Daftar ketidakhadiran dan rotasi (D-09)",
)
def list_availability(
    db: Db,
    resource_id: ResourceIdQuery = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[AvailabilityRead]:
    """Urut tanggal mulai. `date_from`/`date_to` memilih catatan yang bersinggungan dengan
    rentang itu, misalnya satu bulan kalender."""
    return service.list_availability(db, resource_id, date_from, date_to)


@router.post(
    "/availability",
    dependencies=AVAILABILITY_WRITE,
    response_model=AvailabilityRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Catat ketidakhadiran atau rotasi",
)
def create_availability(db: Db, payload: AvailabilityCreate) -> AvailabilityRead:
    try:
        return service.create_availability(db, payload)
    except (service.DataValidationError, service.ConflictError) as exc:
        raise to_http(exc) from exc


@router.patch(
    "/availability/{availability_id}",
    dependencies=AVAILABILITY_WRITE,
    response_model=AvailabilityRead,
    responses=CONFLICT,
    summary="Ubah sebagian kolom catatan ketersediaan",
)
def update_availability(
    db: Db, availability_id: AvailabilityIdPath, payload: AvailabilityUpdate
) -> AvailabilityRead:
    try:
        return service.update_availability(db, availability_id, payload)
    except (
        service.AvailabilityNotFoundError,
        service.DataValidationError,
        service.ConflictError,
    ) as exc:
        raise to_http(exc) from exc


@router.delete(
    "/availability/{availability_id}",
    dependencies=AVAILABILITY_WRITE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus catatan ketersediaan",
)
def delete_availability(db: Db, availability_id: AvailabilityIdPath) -> Response:
    try:
        service.delete_availability(db, availability_id)
    except (service.AvailabilityNotFoundError, service.ConflictError) as exc:
        raise to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/holidays",
    dependencies=MASTER_READ,
    response_model=list[HolidayRead],
    summary="Daftar hari libur (D-11)",
)
def list_holidays(
    db: Db, year: Annotated[int | None, Query(ge=1900, le=2100)] = None
) -> list[HolidayRead]:
    return service.list_holidays(db, year)


@router.post(
    "/holidays",
    dependencies=MASTER_WRITE,
    response_model=HolidayRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Tambah hari libur nasional atau cuti bersama",
)
def create_holiday(db: Db, payload: HolidayCreate) -> HolidayRead:
    try:
        return service.create_holiday(db, payload)
    except service.ConflictError as exc:
        raise to_http(exc) from exc


@router.patch(
    "/holidays/{holiday_date}",
    dependencies=MASTER_WRITE,
    response_model=HolidayRead,
    summary="Ubah nama hari libur",
)
def update_holiday(db: Db, holiday_date: HolidayDatePath, payload: HolidayUpdate) -> HolidayRead:
    try:
        return service.update_holiday(db, parse_path_date(holiday_date), payload)
    except (service.HolidayNotFoundError, service.ConflictError) as exc:
        raise to_http(exc) from exc


@router.delete(
    "/holidays/{holiday_date}",
    dependencies=MASTER_WRITE,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus hari libur",
)
def delete_holiday(db: Db, holiday_date: HolidayDatePath) -> Response:
    try:
        service.delete_holiday(db, parse_path_date(holiday_date))
    except (service.HolidayNotFoundError, service.ConflictError) as exc:
        raise to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# D-10 kejadian perubahan (DIG-149) ada di modul terpisah. Dipasang di akhir berkas supaya
# tidak bentrok dengan router lain yang ditambahkan di awal (misalnya beban non-proyek).
from app.modules.data.change_event_router import router as change_event_router  # noqa: E402

router.include_router(change_event_router)

# "Task saya": blocker dan overrun oleh pelaksana task (DIG-153, DIG-154).
from app.modules.data.my_task_router import router as my_task_router  # noqa: E402

router.include_router(my_task_router)

# Alias identitas anggota antar tool (DIG-24), tabel internal J&C resource_alias.
from app.modules.data.resource_alias_router import router as resource_alias_router  # noqa: E402

router.include_router(resource_alias_router)
