"""Ekspor 11 CSV final sources D-01 s.d. D-11 dalam satu zip (DIG-193, story DIG-44).

Cadangan bagi tWinner bila akses basis data langsung belum tersedia (DATA_CONTRACT bagian 4
butir 4). Nama berkas `<tabel>.csv`, header dan urutan kolom sama dengan Data Dictionary dan
`puti_datasets.xlsx` (urutan kolom tabel sama dengan migrasi).

Izin `data_quality:read` + `workload:read_all` (System Analyst): berkas memuat D-08 beban kerja
dan D-09 ketidakhadiran seluruh anggota, yang menurut DIG-19 hanya untuk pemegang
`workload:read_all`. Administrator Data tidak memegangnya.

Nilai ditulis mentah, tanpa `safe_cell`: berkas ini dibaca program tWinner, dan awalan `'`
akan mengubah datanya. Sanitasi formula tetap ada di CSV laporan kualitas untuk pengguna.
"""

import csv
import io
import zipfile
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import get_db
from app.modules.auth.dependencies import require_permission
from app.modules.auth.permissions import Perm
from app.modules.data.csv_cells import format_value

# Urutan D-01 s.d. D-11.
FINAL_SOURCES = (
    "projects",
    "resources",
    "roles",
    "complexity_levels",
    "tasks",
    "task_dependencies",
    "assignments",
    "workload_items",
    "availability",
    "change_events",
    "holidays",
)

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


def table_csv(db: Session, name: str) -> str:
    table = Base.metadata.tables[name]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(table.columns.keys())
    rows = db.execute(select(table).order_by(*table.primary_key.columns))
    writer.writerows([format_value(value) for value in row] for row in rows)
    return buffer.getvalue()


@router.get(
    "/final-sources.zip",
    dependencies=[Depends(require_permission(Perm.DATA_QUALITY_READ, Perm.WORKLOAD_READ_ALL))],
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}}},
    summary="Ekspor 11 CSV final sources D-01 s.d. D-11 (DIG-193)",
)
def export_final_sources(db: Db) -> Response:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in FINAL_SOURCES:
            archive.writestr(f"{name}.csv", table_csv(db, name).encode("utf-8"))
    filename = f"final_sources_{date.today().isoformat()}.zip"
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
