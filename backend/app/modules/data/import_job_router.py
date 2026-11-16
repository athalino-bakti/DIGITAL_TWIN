"""Pemantauan job impor terjadwal (DIG-128).

Riwayat dan status setiap job dari tabel import_job: kapan jalan, berapa percobaan, berapa
baris yang dibaca dan ditulis, dan pesan error bila gagal. Dipasang langsung di
`app/api/router.py` seperti router pengalihan task, agar tidak bentrok dengan PR modul Data.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.import_job_models import ImportJob
from app.pipeline.config import get_pipeline_settings

router = APIRouter(prefix="/data", tags=["Data"])

# Kualitas data pipeline: dibaca System Analyst dan admin data (sama dengan laporan mutu data).
MONITOR = [Depends(require_permission(Perm.DATA_QUALITY_READ))]

Db = Annotated[Session, Depends(get_db)]
Source = Literal["trello", "project_plan", "teamgit"]
Status = Literal["running", "succeeded", "failed"]


class ImportJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: int
    source: str
    trigger: str
    status: str
    attempts: int
    started_at: datetime
    finished_at: datetime | None
    rows_read: int | None
    rows_written: int | None
    details: dict[str, Any] | None
    error: str | None
    triggered_by: str | None
    stale: bool = Field(
        False,
        description=(
            "Masih running tetapi sudah lebih lama dari IMPORT_STALE_MINUTES: prosesnya "
            "kemungkinan mati. Baris ini baru ditutup failed saat job sumber yang sama "
            "berikutnya dimulai."
        ),
    )


def _read(job: ImportJob, stale_before: datetime) -> ImportJobRead:
    item = ImportJobRead.model_validate(job)
    item.stale = job.status == "running" and job.started_at < stale_before
    return item


def _stale_before() -> datetime:
    return datetime.now(UTC) - timedelta(minutes=get_pipeline_settings().import_stale_minutes)


@router.get("/import-jobs", response_model=list[ImportJobRead], dependencies=MONITOR)
def list_import_jobs(
    db: Db,
    source: Source | None = None,
    job_status: Annotated[Status | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ImportJobRead]:
    statement = select(ImportJob).order_by(ImportJob.started_at.desc(), ImportJob.job_id.desc())
    if source is not None:
        statement = statement.where(ImportJob.source == source)
    if job_status is not None:
        statement = statement.where(ImportJob.status == job_status)
    stale_before = _stale_before()
    return [_read(job, stale_before) for job in db.scalars(statement.limit(limit))]


@router.get("/import-jobs/{job_id}", response_model=ImportJobRead, dependencies=MONITOR)
def get_import_job(db: Db, job_id: Annotated[int, Path(ge=1)]) -> ImportJobRead:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job impor {job_id} tidak ditemukan")
    return _read(job, _stale_before())
