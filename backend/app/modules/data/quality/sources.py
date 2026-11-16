"""Adapter sasaran pemeriksaan (DIG-140): setiap sumber diubah menjadi baris teks per tabel.

Nilai dibaca apa adanya sebagai teks, dengan bentuk CSV kontrak data bagian 5 (tanggal ISO,
boolean `true`/`false`, desimal bertitik). Sel bertipe dari workbook atau basis data diubah ke
bentuk itu, sehingga aturan yang sama berlaku untuk ketiga sasaran.
"""

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.modules.data.quality.engine import SourceRow
from app.modules.data.quality.rules import COLUMNS, PRIMARY_KEY, TABLES


def as_text(value: Any) -> str:
    """Teks bentuk CSV kontrak untuk sel bertipe (workbook, basis data)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return (
            value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat()
        )
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    return str(value)


def _row(table: str, number: int | None, values: dict[str, str]) -> SourceRow:
    return SourceRow(number, values.get(PRIMARY_KEY[table]) or None, values)


def read_csv_folder(folder: Path) -> dict[str, list[SourceRow]]:
    """Berkas `<tabel>.csv` (UTF-8, pemisah koma). Tabel tanpa berkas tidak diperiksa.

    Nomor baris mengikuti urutan rekaman; baris judul kolom = baris 1.
    """
    tables = {}
    for table in TABLES:
        path = Path(folder) / f"{table}.csv"
        if not path.exists():
            continue
        with path.open(encoding="utf-8-sig", newline="") as handle:
            records = csv.DictReader(handle)
            tables[table] = [
                _row(table, number, {c: record.get(c) or "" for c in COLUMNS[table]})
                for number, record in enumerate(records, start=2)
            ]
    return tables


def read_workbook(path: Path) -> dict[str, list[SourceRow]]:
    """Workbook dengan sheet `<tabel>` atau `<tabel>_csv` (dataset dummy dosbim). Baris yang
    semua selnya kosong dilewati; nomor baris mengikuti nomor baris sheet.

    Butuh openpyxl, yang menjadi dependensi aplikasi bersama unggah Project Plan (DIG-25).
    Diimpor di sini supaya adapter lain tetap jalan tanpa paket itu.
    """
    from openpyxl import load_workbook

    book = load_workbook(path, read_only=True, data_only=True)
    try:
        tables = {}
        for table in TABLES:
            name = next((n for n in (table, f"{table}_csv") if n in book.sheetnames), None)
            if name is None:
                continue
            records = book[name].iter_rows(values_only=True)
            header = [as_text(cell) for cell in next(records, ())]
            rows = []
            for number, cells in enumerate(records, start=2):
                values = dict(zip(header, (as_text(cell) for cell in cells)))
                if any(value.strip() for value in values.values()):
                    rows.append(_row(table, number, {c: values.get(c, "") for c in COLUMNS[table]}))
            tables[table] = rows
        return tables
    finally:
        book.close()


def read_database(db: Session) -> dict[str, list[SourceRow]]:
    """Tabel final sources di basis data. Constraint sudah menjaga sebagian aturan; yang
    tersisa (siklus, hari libur, rentang estimasi, requested_by) tetap bisa ditemukan."""
    tables = {}
    for table in TABLES:
        model = Base.metadata.tables[table]
        statement = select(model).order_by(model.c[PRIMARY_KEY[table]])
        tables[table] = [
            _row(table, None, {c: as_text(record[c]) for c in COLUMNS[table]})
            for record in db.execute(statement).mappings()
        ]
    return tables
