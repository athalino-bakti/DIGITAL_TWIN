"""Laporan kualitas data per impor dan daftar baris ditolak (DIG-146, story DIG-32).

Membaca data_quality_result dan rejected_row (DIG-145). Kontrak respons disepakati dengan FE
DIG-147. Dipasang di router modul Data, jadi path-nya berawalan /data.
"""

import csv
import io
from collections import defaultdict
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.import_job_models import ImportJob
from app.modules.data.quality_models import CHARACTERISTICS, DataQualityResult, RejectedRow

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
QUALITY = [Depends(require_permission(Perm.DATA_QUALITY_READ))]
Source = Literal["project_plan", "trello", "teamgit"]
Level = Literal["tolak", "peringatan"]
Characteristic = Literal["completeness", "consistency", "currentness", "traceability"]

LABEL = {
    "completeness": "Kelengkapan",
    "consistency": "Konsistensi",
    "currentness": "Kemutakhiran",
    "traceability": "Keterlacakan",
}


class CharacteristicScore(BaseModel):
    characteristic: str
    label: str
    checked: int
    violated: int
    pass_rate: float | None


class RuleResult(BaseModel):
    rule_id: str
    table: str
    characteristic: str
    level: str
    text: str
    checked: int
    violated: int


class QualitySummary(BaseModel):
    job_id: int | None
    source: str
    file_name: str | None
    project_id: str | None
    validated_at: datetime | None
    rows_checked: int
    rows_rejected: int
    rows_with_warning: int
    pass_rate: float | None
    characteristics: list[CharacteristicScore]
    rules: list[RuleResult]


class RowFinding(BaseModel):
    rule_id: str
    characteristic: str
    level: str
    column: str | None
    value: str | None
    message: str


class RejectedItem(BaseModel):
    source: str
    table: str
    row_number: int | None
    row_key: str | None
    level: str
    findings: list[RowFinding]


class RejectedPage(BaseModel):
    job_id: int
    total: int
    page: int
    page_size: int
    items: list[RejectedItem]


def _rate(checked: int, violated: int) -> float | None:
    return round(1 - violated / checked, 4) if checked else None


def _job(db: Session, job_id: int) -> ImportJob:
    job = db.get(ImportJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Job impor {job_id} tidak ditemukan")
    return job


def _latest_validated(db: Session, source: str) -> ImportJob | None:
    job_id = db.scalar(
        select(func.max(DataQualityResult.job_id))
        .join(ImportJob, ImportJob.job_id == DataQualityResult.job_id)
        .where(ImportJob.source == source, ImportJob.status == "succeeded")
    )
    return db.get(ImportJob, job_id) if job_id else None


def _group_rows(rows: list[RejectedRow]) -> list[RejectedItem]:
    """Temuan per baris sumber; baris bertemuan `tolak` dulu, lalu nomor baris."""
    groups: dict[tuple, list[RejectedRow]] = defaultdict(list)
    for row in rows:
        groups[(row.source, row.table_name, row.row_number, row.row_key)].append(row)
    items = [
        RejectedItem(
            source=source,
            table=table,
            row_number=number,
            row_key=key,
            level="tolak" if any(r.level == "tolak" for r in found) else "peringatan",
            findings=[
                RowFinding(
                    rule_id=r.rule_id,
                    characteristic=r.characteristic,
                    level=r.level,
                    column=r.column_name,
                    value=r.value,
                    message=r.message,
                )
                for r in sorted(found, key=lambda r: (r.rule_id, r.rejected_id))
            ],
        )
        for (source, table, number, key), found in groups.items()
    ]
    items.sort(key=lambda i: (i.level != "tolak", i.row_number is None, i.row_number or 0, i.table))
    return items


def build_summary(db: Session, job: ImportJob | None, source: str) -> QualitySummary:
    results = (
        list(db.scalars(select(DataQualityResult).where(DataQualityResult.job_id == job.job_id)))
        if job
        else []
    )
    findings = (
        list(db.scalars(select(RejectedRow).where(RejectedRow.job_id == job.job_id))) if job else []
    )
    items = _group_rows(findings)
    # Baris yang diperiksa per tabel = jumlah periksa terbesar di antara aturan berbasis baris.
    # Kunci (source, tabel): tabel bernama sama dari dua sumber dihitung terpisah.
    per_table: dict[tuple[str, str], int] = defaultdict(int)
    for r in results:
        if r.characteristic != "currentness":
            key = (r.source, r.table_name)
            per_table[key] = max(per_table[key], r.checked)
    rows_checked = sum(per_table.values())
    rejected = sum(1 for i in items if i.level == "tolak")
    totals = {c: [0, 0] for c in CHARACTERISTICS}
    for r in results:
        totals[r.characteristic][0] += r.checked
        totals[r.characteristic][1] += r.violated
    details = (job.details or {}) if job else {}
    return QualitySummary(
        job_id=job.job_id if job else None,
        source=job.source if job else source,
        file_name=details.get("file_name"),
        project_id=details.get("project_id"),
        validated_at=max((r.checked_at for r in results), default=None),
        rows_checked=rows_checked,
        rows_rejected=rejected,
        rows_with_warning=len(items) - rejected,
        pass_rate=_rate(rows_checked, rejected),
        characteristics=[
            CharacteristicScore(
                characteristic=c,
                label=LABEL[c],
                checked=checked,
                violated=violated,
                pass_rate=_rate(checked, violated),
            )
            for c, (checked, violated) in totals.items()
        ],
        rules=[
            RuleResult(
                rule_id=r.rule_id,
                table=r.table_name,
                characteristic=r.characteristic,
                level=r.level,
                text=r.rule_text,
                checked=r.checked,
                violated=r.violated,
            )
            for r in sorted(results, key=lambda r: (r.rule_id, r.source))
        ],
    )


def _filtered_items(
    db: Session,
    job_id: int,
    level: str | None,
    rule_id: str | None,
    characteristic: str | None,
) -> list[RejectedItem]:
    _job(db, job_id)
    statement = select(RejectedRow).where(RejectedRow.job_id == job_id)
    if rule_id:
        statement = statement.where(RejectedRow.rule_id == rule_id)
    if characteristic:
        statement = statement.where(RejectedRow.characteristic == characteristic)
    items = _group_rows(list(db.scalars(statement)))
    return [i for i in items if level is None or i.level == level]


# Awalan yang membuat Excel/Sheets membaca sel sebagai formula (CSV/formula injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    """Sel teks yang bisa terbaca sebagai formula diawali `'`; angka dibiarkan."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def _csv(name: str, header: list[str], rows: list[list]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows([_safe_cell(cell) for cell in row] for row in rows)
    # BOM supaya Excel membaca UTF-8 dengan benar.
    return Response(
        "﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


JobId = Annotated[int, Query(ge=1)]


@router.get(
    "/quality/summary",
    dependencies=QUALITY,
    response_model=QualitySummary,
    summary="Ringkasan kualitas data satu impor per karakteristik dan per aturan",
)
def quality_summary(
    db: Db, job_id: Annotated[int | None, Query(ge=1)] = None, source: Source = "project_plan"
) -> QualitySummary:
    """Tanpa `job_id`: impor sukses terakhir sumber itu yang sudah divalidasi. Belum pernah
    divalidasi: `job_id` null dan angka 0."""
    job = _job(db, job_id) if job_id else _latest_validated(db, source)
    return build_summary(db, job, source)


@router.get(
    "/quality/rejected-rows",
    dependencies=QUALITY,
    response_model=RejectedPage,
    summary="Baris yang ditolak atau diberi peringatan pada satu impor",
)
def rejected_rows(
    db: Db,
    job_id: JobId,
    level: Level | None = None,
    rule_id: str | None = None,
    characteristic: Characteristic | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RejectedPage:
    # shortcut: dikelompokkan dan dipotong di Python; pindah ke SQL bila temuan per job > 10 ribu.
    items = _filtered_items(db, job_id, level, rule_id, characteristic)
    start = (page - 1) * page_size
    return RejectedPage(
        job_id=job_id,
        total=len(items),
        page=page,
        page_size=page_size,
        items=items[start : start + page_size],
    )


@router.get("/quality/summary.csv", dependencies=QUALITY, summary="Unduh ringkasan per aturan")
def quality_summary_csv(db: Db, job_id: JobId) -> Response:
    summary = build_summary(db, _job(db, job_id), "")
    return _csv(
        f"kualitas_job_{job_id}.csv",
        ["rule_id", "table", "characteristic", "level", "checked", "violated", "pass_rate"],
        [
            [
                r.rule_id,
                r.table,
                r.characteristic,
                r.level,
                r.checked,
                r.violated,
                _rate(r.checked, r.violated),
            ]
            for r in summary.rules
        ],
    )


@router.get("/quality/rejected-rows.csv", dependencies=QUALITY, summary="Unduh temuan per baris")
def rejected_rows_csv(db: Db, job_id: JobId, level: Level | None = None) -> Response:
    items = _filtered_items(db, job_id, level, None, None)
    return _csv(
        f"baris_ditolak_job_{job_id}.csv",
        [
            "source",
            "table",
            "row_number",
            "row_key",
            "level",
            "rule_id",
            "characteristic",
            "column",
            "value",
            "message",
        ],
        [
            [
                i.source,
                i.table,
                i.row_number,
                i.row_key,
                f.level,
                f.rule_id,
                f.characteristic,
                f.column,
                f.value,
                f.message,
            ]
            for i in items
            for f in i.findings
        ],
    )
