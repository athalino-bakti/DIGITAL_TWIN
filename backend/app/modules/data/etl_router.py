"""Endpoint pemicu ETL staging ke tabel final (DIG-134). Dipasang di router modul Data (/data).

Izin `import:run`, sama dengan impor lain. Alur unggah Project Plan dan impor Trello tidak
berubah: ETL dipicu terpisah setelah impor (keputusan Davi 24 Nov).
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.enums import PROJECT_ID_PATTERN
from app.modules.data.etl.load import run

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


@router.post(
    "/etl/run",
    dependencies=[Depends(require_permission(Perm.IMPORT_RUN))],
    summary="Muat staging Project Plan dan Trello ke tasks, task_dependencies, assignments",
    responses={404: {"description": "Proyek belum punya batch Project Plan yang sukses"}},
)
def run_etl(
    db: Db,
    project_id: Annotated[
        str | None, Query(pattern=PROJECT_ID_PATTERN, description="Kosong = semua proyek")
    ] = None,
) -> list[dict[str, Any]]:
    """Laporan per proyek: baris dimuat, diperbarui, tidak berubah, ditolak validator, konflik
    dengan perubahan manual, dan identitas yang belum dipetakan. Aman diulang."""
    reports = run(db, project_id)
    if project_id and reports[0].job_id is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="Proyek belum punya batch Project Plan yang sukses"
        )
    db.commit()
    return [r.as_dict() for r in reports]
