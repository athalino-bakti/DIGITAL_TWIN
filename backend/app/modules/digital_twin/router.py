from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import FORBIDDEN, CurrentUser, require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.enums import PROJECT_ID_PATTERN, RESOURCE_ID_PATTERN, ROLE_ID_PATTERN
from app.modules.digital_twin import heatmap_service, summary_service, timeline_service
from app.modules.digital_twin.heatmap_schemas import WorkloadHeatmap
from app.modules.digital_twin.summary_schemas import BaselineSummary
from app.modules.digital_twin.timeline_schemas import TimelineResponse

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])

Db = Annotated[Session, Depends(get_db)]
BASELINE_READ = [Depends(require_permission(Perm.BASELINE_READ))]


@router.get(
    "/timeline",
    dependencies=BASELINE_READ,
    response_model=TimelineResponse,
    summary="Data Gantt rencana vs aktual (tab Timeline)",
)
def timeline(
    db: Db,
    project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    resource_id: Annotated[str | None, Query(pattern=RESOURCE_ID_PATTERN)] = None,
    as_of: Annotated[
        date | None, Query(description="Tanggal acuan keterlambatan, bawaan hari ini")
    ] = None,
) -> TimelineResponse:
    """Task dikelompokkan per proyek (urut prioritas) lalu per phase, lengkap dengan penanda
    terlambat, kejadian perubahan (D-10), dan hari libur (D-11) dalam rentang tanggalnya."""
    return timeline_service.build_timeline(db, as_of or date.today(), project_id, resource_id)


@router.get(
    "/summary",
    dependencies=BASELINE_READ,
    response_model=BaselineSummary,
    summary="Kartu ringkasan baseline beserta daftar detailnya (DIG-40)",
)
def summary(
    db: Db,
    as_of: Annotated[date | None, Query(description="Tanggal acuan, bawaan hari ini")] = None,
) -> BaselineSummary:
    """Proyek aktif, proyek lewat target, resource overload (menunggu RLI), dan resource
    multi-role. Aturan tiap kartu ada di `summary_service`."""
    return summary_service.build_summary(db, as_of or date.today())


@router.get(
    "/workload-heatmap",
    response_model=WorkloadHeatmap,
    responses={403: {"description": "Tanpa izin workload:read_all maupun workload:read_own"}},
    summary="Heatmap Resource Load Index per anggota per minggu (DIG-188)",
)
def workload_heatmap(
    db: Db,
    user: CurrentUser,
    start: Annotated[
        date | None, Query(description="Tanggal di minggu pertama, dibulatkan ke Senin")
    ] = None,
    weeks: Annotated[
        int, Query(ge=1, le=heatmap_service.MAX_WEEKS)
    ] = heatmap_service.DEFAULT_WEEKS,
    role_id: Annotated[str | None, Query(pattern=ROLE_ID_PATTERN)] = None,
    project_id: Annotated[str | None, Query(pattern=PROJECT_ID_PATTERN)] = None,
    resource_id: Annotated[str | None, Query(pattern=RESOURCE_ID_PATTERN)] = None,
    as_of: Annotated[
        date | None, Query(description="Tanggal acuan task terbuka, bawaan hari ini")
    ] = None,
) -> WorkloadHeatmap:
    """Pemegang `workload:read_all` melihat semua anggota. Pemegang `workload:read_own` saja
    hanya melihat anggota yang tertaut ke akunnya; filter `role_id` dan `resource_id` diabaikan.
    Formula RLI masih provisional (`formula_version`)."""
    today = date.today()
    as_of = as_of or today
    start = start or heatmap_service.default_start(today)
    permissions = auth_service.get_user_permissions(db, user.user_id)
    if Perm.WORKLOAD_READ_ALL not in permissions:
        if Perm.WORKLOAD_READ_OWN not in permissions:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail=FORBIDDEN)
        if user.resource_id is None:
            return heatmap_service.empty_heatmap(db, start, weeks, as_of)
        role_id, resource_id = None, user.resource_id
    return heatmap_service.build_heatmap(
        db, start, weeks, as_of, role_id=role_id, project_id=project_id, resource_id=resource_id
    )
