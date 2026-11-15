"""Layanan D-08 workload_items, beban non-proyek (DIG-30).

Mencakup CRUD (DIG-136), impor CSV berformat Data Dictionary (DIG-136), serta aturan tanggal
dan hotfix (DIG-138). Aturan dipakai bersama oleh formulir dan impor agar keduanya menolak
data yang sama.

Aturan hotfix mengikuti DATA_CONTRACT D-08 ("penanda hotfix production") dan pola data
sintetis DIG-16: hotfix adalah tiket untuk aplikasi yang sudah rilis di production.
"""

import csv
import io
from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.modules.data.enums import Severity, WorkloadItemType
from app.modules.data.models import Project, Resource, WorkloadItem
from app.modules.data.service import (
    ConflictError,
    DataValidationError,
    FieldError,
    NotFoundError,
    commit,
    next_id,
)
from app.modules.data.workload_schemas import (
    ImportRowError,
    WorkloadImportRequest,
    WorkloadImportResult,
    WorkloadItemCreate,
    WorkloadItemRead,
    WorkloadItemUpdate,
)


class WorkloadItemNotFoundError(NotFoundError):
    label = "Item beban non-proyek"


# Urutan kolom D-08 pada Data Dictionary (DATA_CONTRACT bagian 6).
CSV_COLUMNS = (
    "item_id",
    "resource_id",
    "item_type",
    "related_project_id",
    "received_date",
    "started_date",
    "resolved_date",
    "severity",
    "is_hotfix",
)
NOT_NULL = frozenset({"resource_id", "item_type", "received_date", "is_hotfix"})
MAX_IMPORT_ROWS = 50_000
MAX_REPORTED_ERRORS = 500


# --- aturan (DIG-138) ---


def check_workload_rules(
    values: Mapping[str, Any], launch_dates: Mapping[str, date | None]
) -> list[FieldError]:
    """Aturan tanggal dan hotfix untuk satu item.

    `launch_dates` memetakan setiap project_id yang terdaftar ke `actual_launch_date`-nya.
    Proyek yang tidak ada di peta dianggap tidak terdaftar.
    """
    errors: list[FieldError] = []
    received = values["received_date"]
    started = values.get("started_date")
    resolved = values.get("resolved_date")
    if started is not None and started < received:
        errors.append(
            FieldError(
                "started_date", "Tanggal mulai tidak boleh sebelum tanggal diterima", "date_order"
            )
        )
    if resolved is not None and resolved < received:
        errors.append(
            FieldError(
                "resolved_date",
                "Tanggal selesai tidak boleh sebelum tanggal diterima",
                "date_order",
            )
        )
    elif resolved is not None and started is not None and resolved < started:
        errors.append(
            FieldError(
                "resolved_date", "Tanggal selesai tidak boleh sebelum tanggal mulai", "date_order"
            )
        )

    project = values.get("related_project_id")
    if project is not None and project not in launch_dates:
        errors.append(
            FieldError(
                "related_project_id", f"Proyek {project} tidak terdaftar", "project_not_found"
            )
        )
    if not values["is_hotfix"]:
        return errors

    if values["item_type"] != WorkloadItemType.TICKET:
        errors.append(
            FieldError("is_hotfix", "Hotfix hanya untuk item berjenis tiket", "hotfix_needs_ticket")
        )
    if project is None:
        errors.append(
            FieldError(
                "related_project_id",
                "Hotfix wajib dikaitkan dengan aplikasi yang sudah rilis",
                "hotfix_needs_project",
            )
        )
    elif project in launch_dates:
        launched = launch_dates[project]
        if launched is None or launched > received:
            when = "belum rilis" if launched is None else f"baru rilis {launched.isoformat()}"
            errors.append(
                FieldError(
                    "related_project_id",
                    f"Hotfix hanya untuk aplikasi yang sudah rilis di production; {project} {when}",
                    "hotfix_needs_release",
                )
            )
    return errors


def item_status(item: WorkloadItem) -> str:
    if item.resolved_date is not None:
        return "resolved"
    if item.started_date is not None:
        return "in_progress"
    return "waiting"


def launch_dates_for(db: Session, project_ids: set[str]) -> dict[str, date | None]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(Project.project_id, Project.actual_launch_date).where(
            Project.project_id.in_(project_ids)
        )
    )
    return {project_id: launched for project_id, launched in rows}


def validate_item(db: Session, values: Mapping[str, Any]) -> None:
    errors: list[FieldError] = []
    if db.get(Resource, values["resource_id"]) is None:
        errors.append(
            FieldError(
                "resource_id",
                f"Anggota {values['resource_id']} tidak terdaftar",
                "resource_not_found",
            )
        )
    project = values.get("related_project_id")
    errors += check_workload_rules(values, launch_dates_for(db, {project} if project else set()))
    if errors:
        raise DataValidationError(errors)


# --- CRUD (DIG-136) ---


def to_read(item: WorkloadItem, resource_name: str, project_name: str | None) -> WorkloadItemRead:
    return WorkloadItemRead(
        item_id=item.item_id,
        resource_id=item.resource_id,
        resource_name=resource_name,
        item_type=item.item_type,
        related_project_id=item.related_project_id,
        project_name=project_name,
        received_date=item.received_date,
        started_date=item.started_date,
        resolved_date=item.resolved_date,
        severity=item.severity,
        is_hotfix=item.is_hotfix,
        status=item_status(item),
    )


def _read_one(db: Session, item: WorkloadItem) -> WorkloadItemRead:
    resource_name = db.scalar(
        select(Resource.resource_name).where(Resource.resource_id == item.resource_id)
    )
    project_name = None
    if item.related_project_id is not None:
        project_name = db.scalar(
            select(Project.project_name).where(Project.project_id == item.related_project_id)
        )
    return to_read(item, resource_name or "", project_name)


def list_workload_items(
    db: Session,
    resource_id: str | None = None,
    item_type: WorkloadItemType | None = None,
    related_project_id: str | None = None,
    open_only: bool = False,
    received_from: date | None = None,
    received_to: date | None = None,
) -> list[WorkloadItemRead]:
    """Terbaru lebih dulu menurut tanggal diterima."""
    query = (
        select(WorkloadItem, Resource.resource_name, Project.project_name)
        .join(Resource, Resource.resource_id == WorkloadItem.resource_id)
        .outerjoin(Project, Project.project_id == WorkloadItem.related_project_id)
        .order_by(WorkloadItem.received_date.desc(), WorkloadItem.item_id.desc())
    )
    if resource_id is not None:
        query = query.where(WorkloadItem.resource_id == resource_id)
    if item_type is not None:
        query = query.where(WorkloadItem.item_type == item_type)
    if related_project_id is not None:
        query = query.where(WorkloadItem.related_project_id == related_project_id)
    if open_only:
        query = query.where(WorkloadItem.resolved_date.is_(None))
    if received_from is not None:
        query = query.where(WorkloadItem.received_date >= received_from)
    if received_to is not None:
        query = query.where(WorkloadItem.received_date <= received_to)
    return [to_read(item, resource, project) for item, resource, project in db.execute(query)]


def get_workload_item(db: Session, item_id: str) -> WorkloadItem:
    item = db.get(WorkloadItem, item_id)
    if item is None:
        raise WorkloadItemNotFoundError(item_id)
    return item


def next_workload_item_id(db: Session, also_taken: list[str] = ()) -> str:
    existing = list(db.scalars(select(WorkloadItem.item_id)))
    return next_id(existing + list(also_taken), "WLI", width=4)


def create_workload_item(db: Session, payload: WorkloadItemCreate) -> WorkloadItemRead:
    values = payload.model_dump()
    validate_item(db, values)
    if values["item_id"] is None:
        values["item_id"] = next_workload_item_id(db)
    elif db.get(WorkloadItem, values["item_id"]) is not None:
        raise ConflictError(f"ID {values['item_id']} sudah dipakai item lain", field="item_id")
    item = WorkloadItem(**values)
    db.add(item)
    commit(db)
    return _read_one(db, item)


def update_workload_item(
    db: Session, item_id: str, payload: WorkloadItemUpdate
) -> WorkloadItemRead:
    item = get_workload_item(db, item_id)
    changes = payload.model_dump(exclude_unset=True)
    errors = [
        FieldError(field, "Kolom ini wajib diisi", "missing")
        for field, value in changes.items()
        if value is None and field in NOT_NULL
    ]
    if errors:
        raise DataValidationError(errors)
    values = {c.key: getattr(item, c.key) for c in WorkloadItem.__table__.columns} | changes
    validate_item(db, values)
    for field, value in changes.items():
        setattr(item, field, value)
    commit(db)
    return _read_one(db, item)


def delete_workload_item(db: Session, item_id: str) -> None:
    db.delete(get_workload_item(db, item_id))
    commit(db)


# --- impor CSV (DIG-136) ---

_VALUE_HINT = {
    "item_id": "format WLI-0001",
    "resource_id": "format RES-001",
    "related_project_id": "format PRJ-001",
    "item_type": "operational atau ticket",
    "severity": ", ".join(Severity),
}


def _pydantic_message(error: Mapping[str, Any]) -> str:
    field = str(error["loc"][0]) if error.get("loc") else ""
    kind = error.get("type", "")
    if kind.startswith("bool"):
        return "Isi true atau false"
    # Sel kosong dibaca sebagai None, sehingga kolom wajib yang kosong gagal sebagai tipe salah.
    if kind == "missing" or ("input" in error and error["input"] is None):
        return "Wajib diisi"
    if kind in ("string_pattern_mismatch", "enum", "literal_error"):
        return f"Nilai tidak sah, gunakan {_VALUE_HINT.get(field, 'nilai yang benar')}"
    if kind == "value_error":
        return str(error.get("ctx", {}).get("error", error.get("msg", "Nilai tidak sah")))
    return str(error.get("msg", "Nilai tidak sah"))


def parse_workload_csv(
    content: str,
) -> tuple[list[tuple[int, dict[str, Any]]], list[ImportRowError], int]:
    """Baca CSV D-08 tanpa menyentuh basis data.

    Mengembalikan (baris valid beserta nomor barisnya, kesalahan format, jumlah baris data).
    Sel kosong menjadi NULL. Kolom boleh berurutan apa saja, tetapi kesembilan kolom
    Data Dictionary wajib ada dan kolom lain ditolak.
    """
    reader = csv.DictReader(io.StringIO(content.removeprefix("﻿")))
    header = [name.strip() for name in reader.fieldnames or []]
    missing = [c for c in CSV_COLUMNS if c not in header]
    unknown = [c for c in header if c not in CSV_COLUMNS]
    if not header:
        return [], [ImportRowError(row=1, item_id=None, field=None, message="Berkas kosong")], 0
    if missing or unknown or len(set(header)) != len(header):
        parts = []
        if missing:
            parts.append("kolom hilang: " + ", ".join(missing))
        if unknown:
            parts.append("kolom tidak dikenal: " + ", ".join(unknown))
        if len(set(header)) != len(header):
            parts.append("ada nama kolom ganda")
        message = "Judul kolom tidak sesuai Data Dictionary: " + "; ".join(parts)
        return [], [ImportRowError(row=1, item_id=None, field=None, message=message)], 0
    reader.fieldnames = header

    rows: list[tuple[int, dict[str, Any]]] = []
    errors: list[ImportRowError] = []
    total = 0
    for record in reader:
        line = reader.line_num
        if not any((value or "").strip() for key, value in record.items() if key is not None):
            continue  # baris kosong di akhir berkas
        total += 1
        raw_id = (record.get("item_id") or "").strip() or None
        if record.get(None):
            errors.append(
                ImportRowError(
                    row=line, item_id=raw_id, field=None, message="Jumlah kolom melebihi judul"
                )
            )
            continue
        values: dict[str, Any] = {}
        for column in CSV_COLUMNS:
            cell = (record.get(column) or "").strip()
            values[column] = cell or None
        flag = values["is_hotfix"]
        if isinstance(flag, str) and flag.lower() in ("true", "false"):
            values["is_hotfix"] = flag.lower() == "true"
        try:
            item = WorkloadItemCreate.model_validate(values)
        except ValidationError as exc:
            for error in exc.errors():
                field = str(error["loc"][0]) if error.get("loc") else None
                errors.append(
                    ImportRowError(
                        row=line, item_id=raw_id, field=field, message=_pydantic_message(error)
                    )
                )
            continue
        rows.append((line, item.model_dump()))
    return rows, errors, total


def import_workload_items(db: Session, request: WorkloadImportRequest) -> WorkloadImportResult:
    """Periksa seluruh berkas, lalu simpan semuanya atau tidak sama sekali.

    Baris dengan item_id yang sudah ada memperbarui item itu, sehingga impor ulang berkas
    yang sama tidak menggandakan data. Baris tanpa item_id mendapat nomor WLI berikutnya.
    """
    rows, errors, total = parse_workload_csv(request.content)
    if total > MAX_IMPORT_ROWS:
        errors.insert(
            0,
            ImportRowError(
                row=1,
                item_id=None,
                field=None,
                message=f"Berkas berisi {total} baris, batasnya {MAX_IMPORT_ROWS}",
            ),
        )

    first_row: dict[str, int] = {}
    for line, values in rows:
        item_id = values["item_id"]
        if item_id is None:
            continue
        if item_id in first_row:
            errors.append(
                ImportRowError(
                    row=line,
                    item_id=item_id,
                    field="item_id",
                    message=f"ID sudah muncul di baris {first_row[item_id]}",
                )
            )
        else:
            first_row[item_id] = line

    resource_ids = {values["resource_id"] for _, values in rows}
    known_resources = set(
        db.scalars(select(Resource.resource_id).where(Resource.resource_id.in_(resource_ids)))
    )
    launch_dates = launch_dates_for(
        db, {values["related_project_id"] for _, values in rows if values["related_project_id"]}
    )
    for line, values in rows:
        if values["resource_id"] not in known_resources:
            errors.append(
                ImportRowError(
                    row=line,
                    item_id=values["item_id"],
                    field="resource_id",
                    message=f"Anggota {values['resource_id']} tidak terdaftar",
                )
            )
        errors.extend(
            ImportRowError(
                row=line, item_id=values["item_id"], field=error.field, message=error.message
            )
            for error in check_workload_rules(values, launch_dates)
        )

    given_ids = [values["item_id"] for _, values in rows if values["item_id"]]
    existing = set(
        db.scalars(select(WorkloadItem.item_id).where(WorkloadItem.item_id.in_(given_ids)))
    )
    updated = sum(1 for item_id in given_ids if item_id in existing)
    inserted = len(rows) - updated
    errors.sort(key=lambda e: e.row)

    result = WorkloadImportResult(
        dry_run=request.dry_run,
        applied=False,
        total=total,
        inserted=inserted,
        updated=updated,
        error_count=len(errors),
        errors=errors[:MAX_REPORTED_ERRORS],
    )
    if errors or request.dry_run or not rows:
        return result

    # Nomor berikutnya dihitung sekali, lalu dinaikkan per baris tanpa query ulang.
    first = next_workload_item_id(db, given_ids)
    digits = first.removeprefix("WLI-")
    number, width = int(digits), len(digits)
    for _, values in rows:
        if values["item_id"] is None:
            values["item_id"] = f"WLI-{number:0{width}d}"
            number += 1
    statement = insert(WorkloadItem)
    columns = {c: statement.excluded[c] for c in CSV_COLUMNS if c != "item_id"}
    db.execute(
        statement.on_conflict_do_update(index_elements=["item_id"], set_=columns),
        [values for _, values in rows],
    )
    commit(db)
    return result.model_copy(update={"applied": True})
