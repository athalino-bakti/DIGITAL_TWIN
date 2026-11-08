from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.data import service
from app.modules.data.enums import COMPLEXITY_ID_PATTERN, PROJECT_ID_PATTERN, ProjectStatus
from app.modules.data.schemas import (
    ComplexityRead,
    ComplexityUpdate,
    ProjectCreate,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter(prefix="/data", tags=["Data"])

Db = Annotated[Session, Depends(get_db)]
ProjectIdPath = Annotated[str, Path(pattern=PROJECT_ID_PATTERN, examples=["PRJ-001"])]
ComplexityIdPath = Annotated[str, Path(pattern=COMPLEXITY_ID_PATTERN, examples=["CX-M"])]

CONFLICT = {status.HTTP_409_CONFLICT: {"description": "Bentrok dengan data lain"}}
NOT_FOUND = {status.HTTP_404_NOT_FOUND: {"description": "Proyek tidak ditemukan"}}


def to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, service.NotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=f"{exc.label} tidak ditemukan")
    if isinstance(exc, service.DataValidationError):
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=[error.as_detail() for error in exc.errors],
        )
    if isinstance(exc, service.ProjectConflictError):
        detail: dict = {"msg": exc.message}
        if exc.field:
            detail["loc"] = ["body", exc.field]
        return HTTPException(status.HTTP_409_CONFLICT, detail=detail)
    raise exc


@router.get("/projects", response_model=list[ProjectRead], summary="Daftar proyek (D-01)")
def list_projects(
    db: Db,
    status_filter: Annotated[list[ProjectStatus] | None, Query(alias="status")] = None,
    active_only: bool = False,
) -> list[ProjectRead]:
    """Urut dari prioritas tertinggi (`priority_rank` 1)."""
    return service.list_projects(db, status=status_filter, active_only=active_only)


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    responses=CONFLICT,
    summary="Tambah proyek",
)
def create_project(db: Db, payload: ProjectCreate) -> ProjectRead:
    try:
        return service.create_project(db, payload)
    except (service.DataValidationError, service.ProjectConflictError) as exc:
        raise to_http(exc) from exc


@router.get(
    "/projects/{project_id}", response_model=ProjectRead, responses=NOT_FOUND, summary="Detail"
)
def get_project(db: Db, project_id: ProjectIdPath) -> ProjectRead:
    try:
        return service.to_read(service.get_project(db, project_id))
    except service.ProjectNotFoundError as exc:
        raise to_http(exc) from exc


@router.patch(
    "/projects/{project_id}",
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
        service.ProjectConflictError,
    ) as exc:
        raise to_http(exc) from exc


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
    summary="Hapus proyek yang belum dipakai data lain",
)
def delete_project(db: Db, project_id: ProjectIdPath) -> Response:
    try:
        service.delete_project(db, project_id)
    except (service.ProjectNotFoundError, service.ProjectConflictError) as exc:
        raise to_http(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/complexity-levels",
    response_model=list[ComplexityRead],
    summary="Daftar level kompleksitas (D-04)",
)
def list_complexity_levels(db: Db) -> list[ComplexityRead]:
    """Urut dari level tersulit, beserta jumlah task yang memakai tiap level."""
    return service.list_complexity_levels(db)


@router.patch(
    "/complexity-levels/{complexity_id}",
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
        service.ProjectConflictError,
    ) as exc:
        raise to_http(exc) from exc
