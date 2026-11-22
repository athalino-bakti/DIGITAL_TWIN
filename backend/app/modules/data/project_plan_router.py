"""Unggah Project Plan CSV/XLSX ke staging (DIG-114, story DIG-25).

`dry_run=true` (bawaan) hanya membaca dan memetakan kolom untuk pratinjau, tanpa membuat
import_job dan tanpa menulis staging. `dry_run=false` menjalankan job `project_plan` lewat runner
pipeline (DIG-127), sehingga setiap impor tercatat di import_job, termasuk yang gagal karena
struktur berkasnya rusak. Normalisasi, pencocokan PIC, dan load ke D-05/D-06 adalah DIG-29.

Router ini dipasang di router modul Data (`router.include_router`), sehingga path-nya ikut
berawalan /data.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import get_db
from app.integrations.project_plan.parser import (
    ProjectPlanParseResult,
    StructureError,
    parse_project_plan,
    read_table,
)
from app.modules.auth.dependencies import require_permission
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import Perm

# Modul router Data diimpor sebagai objek modul dan `to_http` dipanggil saat request, karena
# router.py mengimpor modul ini ketika ia sendiri belum selesai dimuat.
from app.modules.data import router as data_routes
from app.modules.data.enums import PROJECT_ID_PATTERN
from app.modules.data.project_plan_staging import same_file_job_id, save_project_plan
from app.modules.data.service import DataValidationError, FieldError
from app.modules.data.workload_schemas import ImportRowError
from app.pipeline.config import get_pipeline_settings
from app.pipeline.jobs import JobOutcome, PermanentJobError
from app.pipeline.runner import JobAlreadyRunning, run_job

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Importer = Annotated[AppUser, Depends(require_permission(Perm.IMPORT_RUN))]

MAX_BYTES = 5 * 1024 * 1024
PREVIEW_ROWS = 20
EXTENSIONS = (".csv", ".xlsx")
FILE_PROJECT_ID = re.compile(r"PRJ-[0-9]{3,}")


class PreviewRow(BaseModel):
    row: int = Field(description="Nomor baris di berkas, baris judul kolom adalah baris 1")
    values: dict[str, str | None]


class ProjectPlanImportResult(BaseModel):
    dry_run: bool
    applied: bool = Field(description="true bila baris benar-benar ditulis ke staging")
    project_id: str
    project_id_source: Literal["parameter", "file_name"]
    file_name: str
    file_type: Literal["csv", "xlsx"]
    file_sha256: str
    sheet_name: str | None
    sheets: list[str] = Field(description="Daftar sheet XLSX; kosong untuk CSV")
    delimiter: str | None = Field(description="Pemisah CSV yang terdeteksi")
    mapping: dict[str, str] = Field(description="Judul kolom berkas -> atribut staging")
    unmapped_headers: list[str] = Field(description="Kolom yang hanya disimpan di raw")
    missing_required: list[str]
    missing_optional: list[str]
    total_rows: int = Field(description="Baris data yang akan/sudah masuk staging")
    skipped_blank_rows: list[int]
    typed_cells: dict[str, int] = Field(
        description="XLSX: jumlah sel bertipe tanggal/angka per kolom, ditulis ISO/titik desimal"
    )
    preview_rows: list[PreviewRow] = Field(description=f"Paling banyak {PREVIEW_ROWS} baris")
    errors: list[ImportRowError] = Field(description="Masalah struktur; kosong berarti siap impor")
    same_file_job_id: int | None = Field(
        description="Job sukses terakhir proyek ini yang berkasnya identik (peringatan)"
    )
    job_id: int | None = None
    job_status: str | None = None
    rows_read: int | None = None
    rows_written: int | None = None


def _invalid(field: str, message: str, error_type: str) -> HTTPException:
    return data_routes.to_http(DataValidationError([FieldError(field, message, error_type)]))


def _project_id(given: str | None, file_name: str) -> tuple[str, str]:
    if given:
        if not re.fullmatch(PROJECT_ID_PATTERN, given):
            raise _invalid("project_id", "Gunakan format PRJ-xxx", "project_id_format")
        return given, "parameter"
    if found := FILE_PROJECT_ID.search(Path(file_name).stem):
        return found.group(), "file_name"
    raise _invalid(
        "project_id",
        "Isi project_id atau beri nama berkas project_plan_PRJ-xxx",
        "project_id_missing",
    )


def _column_map(value: str | None) -> dict[str, str | None] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict) or not all(
        isinstance(k, str) and (v is None or isinstance(v, str)) for k, v in parsed.items()
    ):
        raise _invalid(
            "column_map", 'Gunakan objek JSON {"judul kolom": "atribut" atau null}', "json"
        )
    return parsed


def _errors(messages: list[str]) -> list[ImportRowError]:
    return [ImportRowError(row=1, item_id=None, field=None, message=m) for m in messages]


@router.post(
    "/imports/project-plan",
    response_model=ProjectPlanImportResult,
    responses={
        status.HTTP_409_CONFLICT: {"description": "Impor Project Plan lain masih berjalan"},
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "Berkas lebih dari 5 MB"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Parameter tidak sah, atau impor gagal (detail memuat job_id)"
        },
    },
    summary="Unggah Project Plan CSV/XLSX ke staging (pratinjau dulu dengan dry_run)",
)
def import_project_plan(
    db: Db,
    user: Importer,
    file: Annotated[UploadFile, File(description="Project Plan .csv (UTF-8) atau .xlsx")],
    project_id: Annotated[
        str | None, Form(description="PRJ-xxx; kosong = diambil dari nama berkas")
    ] = None,
    dry_run: Annotated[bool, Form(description="true hanya pratinjau, tanpa menyimpan")] = True,
    sheet: Annotated[str | None, Form(description="Sheet XLSX; kosong = sheet pertama")] = None,
    column_map: Annotated[
        str | None,
        Form(description='JSON {"judul kolom": "atribut" atau null}, menimpa pemetaan bawaan'),
    ] = None,
) -> ProjectPlanImportResult:
    file_name = Path(file.filename or "").name
    if Path(file_name).suffix.lower() not in EXTENSIONS:
        raise _invalid("file", "Berkas harus .csv atau .xlsx", "file_type")
    data = file.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Berkas lebih dari 5 MB")
    project, source = _project_id(project_id, file_name)
    mapping = _column_map(column_map)
    digest = hashlib.sha256(data).hexdigest()

    result: ProjectPlanParseResult | None = None
    problems: list[str] = []
    try:
        result = parse_project_plan(read_table(data, file_name, sheet), mapping)
        problems = result.errors
    except StructureError as exc:
        problems = [str(exc)]

    table = result.table if result else None
    response = ProjectPlanImportResult(
        dry_run=dry_run,
        applied=False,
        project_id=project,
        project_id_source=source,
        file_name=file_name,
        file_type=Path(file_name).suffix.lower().lstrip("."),
        file_sha256=digest,
        sheet_name=table.sheet_name if table else None,
        sheets=table.sheets if table else [],
        delimiter=table.delimiter if table else None,
        mapping=result.mapping if result else {},
        unmapped_headers=result.unmapped_headers if result else [],
        missing_required=result.missing_required if result else [],
        missing_optional=result.missing_optional if result else [],
        total_rows=result.total_rows if result else 0,
        skipped_blank_rows=result.skipped_blank_rows if result else [],
        typed_cells=table.typed_cells if table else {},
        preview_rows=[
            PreviewRow(row=row.row_number, values=row.values)
            for row in (result.rows[:PREVIEW_ROWS] if result else [])
        ],
        errors=_errors(problems),
        same_file_job_id=same_file_job_id(db, project, digest),
    )
    if dry_run:
        return response

    def job_fn(work: Session, settings, job_id: int) -> JobOutcome:
        if problems or result is None:
            raise PermanentJobError("; ".join(problems))
        written = save_project_plan(work, result, job_id, project, file_name)
        work.commit()
        return JobOutcome(
            rows_read=result.total_rows,
            rows_written=written,
            details={
                "project_id": project,
                "file_name": file_name,
                "sheet_name": response.sheet_name,
                "file_sha256": digest,
                "mapping": response.mapping,
                "unmapped_headers": response.unmapped_headers,
                "skipped_blank_rows": response.skipped_blank_rows,
                "typed_cells": response.typed_cells,
            },
        )

    # Satu percobaan saja: pengunggah menunggu respons, dan berkasnya bisa diunggah ulang.
    # Kegagalan langsung terlihat di respons, jadi tidak perlu notifikasi webhook.
    settings = get_pipeline_settings().model_copy(update={"import_max_attempts": 1})
    try:
        job = run_job(
            "project_plan",
            sessionmaker(bind=db.get_bind(), autoflush=False, expire_on_commit=False),
            settings,
            trigger="manual",
            triggered_by=user.username,
            job_fn=job_fn,
            notifier=lambda settings, message: False,
        )
    except JobAlreadyRunning as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"msg": f"Impor Project Plan lain masih berjalan (job {exc.job_id})"},
        ) from exc

    if job.status != "succeeded":
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "msg": "Impor Project Plan gagal",
                "job_id": job.job_id,
                "error": job.error,
                "errors": [e.model_dump() for e in response.errors],
            },
        )
    return response.model_copy(
        update={
            "applied": True,
            "job_id": job.job_id,
            "job_status": job.status,
            "rows_read": job.rows_read,
            "rows_written": job.rows_written,
        }
    )
