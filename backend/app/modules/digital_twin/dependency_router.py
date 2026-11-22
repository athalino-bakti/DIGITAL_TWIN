"""Endpoint graf dependency dan jalur kritis (DIG-42, DIG-182).

Router sendiri dengan prefix /digital-twin dan dipasang di `app/api/router.py`, supaya tidak
bentrok dengan PR lain yang mengisi `digital_twin/router.py`.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.enums import PROJECT_ID_PATTERN, TASK_ID_PATTERN
from app.modules.data.router import to_http
from app.modules.data.service import DataValidationError
from app.modules.digital_twin import dependency_service as service
from app.modules.digital_twin.dependency_schemas import DependencyGraph

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])

Db = Annotated[Session, Depends(get_db)]
BASELINE_READ = [Depends(require_permission(Perm.BASELINE_READ))]


@router.get(
    "/dependency",
    dependencies=BASELINE_READ,
    response_model=DependencyGraph,
    responses={status.HTTP_404_NOT_FOUND: {"description": "Proyek tidak ditemukan"}},
    summary="Graf dependency, jalur kritis, dan dampak keterlambatan satu proyek",
)
def dependency_graph(
    db: Db,
    project_id: Annotated[str, Query(pattern=PROJECT_ID_PATTERN)],
    task_id: Annotated[
        str | None,
        Query(pattern=TASK_ID_PATTERN, description="Task yang keterlambatannya dirambatkan"),
    ] = None,
    delay_days: Annotated[
        float | None,
        Query(ge=0, le=365, description="Ganti keterlambatan task terpilih (hari kerja)"),
    ] = None,
    as_of: Annotated[
        date | None, Query(description="Tanggal acuan keterlambatan, bawaan hari ini")
    ] = None,
) -> DependencyGraph:
    """Jalur kritis dihitung dari dependency hard dengan durasi `estimated_days`. Bila
    `task_id` diisi, tiap task turunan membawa `impact_days` = keterlambatan x
    `propagation_factor` sepanjang jalurnya (dampak terbesar bila ada beberapa jalur)."""
    try:
        return service.build_dependency_graph(
            db, project_id, as_of or date.today(), task_id, delay_days
        )
    except (service.ProjectNotFoundError, DataValidationError) as exc:
        raise to_http(exc) from exc
