from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.enums import PROJECT_ID_PATTERN, RESOURCE_ID_PATTERN
from app.modules.digital_twin import timeline_service
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
