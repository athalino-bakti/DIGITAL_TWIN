"""Parser Project Plan CSV/XLSX ke baris staging_project_plan (DIG-114).

Parser murni: tidak menyentuh basis data. Penyimpanan ada di
`app.modules.data.project_plan_staging`.

Aturan:
- Nilai sel disimpan apa adanya sebagai teks, tanpa strip dan tanpa normalisasi. Cacat isi
  (format tanggal, PIC tak dikenal, baris ganda, sel wajib kosong, siklus dependency) tetap
  masuk staging; menolaknya tugas validator DIG-31, menormalisasinya tugas ETL DIG-29.
- Yang ditolak hanya masalah struktur berkas: tidak terbaca, kosong, nama kolom ganda, kolom
  wajib (`task_code`, `task_name`) tidak ditemukan, atau melebihi batas baris.
- Baris yang semua selnya kosong dilewati dan nomornya dicatat.
- Nomor baris mengikuti spreadsheet: baris judul kolom = baris 1.
- CSV: UTF-8 dengan atau tanpa BOM; pemisah `;` bila baris judul memuat lebih banyak `;`
  daripada `,` (ekspor Excel berlokal Indonesia), selain itu `,`.
- XLSX: sheet pertama atau yang dipilih. Sel bertipe tanggal ditulis ISO (`2026-09-14`), angka
  dengan titik desimal (`2.5`, bilangan bulat tanpa desimal), lalu jumlahnya dicatat per kolom
  di `typed_cells`. Rumus dibaca dari nilai tersimpan terakhir.
"""

import csv
import io
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.modules.data.staging_models import PROJECT_PLAN_FIELDS

REQUIRED = ("task_code", "task_name")
MAX_ROWS = 10_000
EXTRA_KEY = "_lebih"  # sel di luar kolom judul, disimpan di raw

# Judul kolom templat Project Plan (synthetic PLAN_HEADER) dan sinonimnya, dalam bentuk kunci
# `_key`. Nama atribut sendiri (task_code, planned_start, ...) juga dikenali.
_SYNONYMS = {
    "task_code": ("kode", "kode task", "id task", "task id", "task_id"),
    "feature_name": ("fitur", "nama fitur", "feature"),
    "task_name": ("task", "nama task", "tugas"),
    "role_label": ("peran", "role", "required_role_id"),
    "pic": ("penanggung jawab", "assignee"),
    "complexity_label": ("kompleksitas", "complexity", "complexity_id"),
    "priority": ("prioritas", "priority_rank"),
    "estimated_days": ("estimasi (hari)", "estimasi", "estimasi hari"),
    "planned_start": ("mulai rencana", "rencana mulai"),
    "planned_finish": ("selesai rencana", "rencana selesai"),
    "actual_start": ("mulai aktual", "aktual mulai"),
    "actual_finish": ("selesai aktual", "aktual selesai"),
    "status_label": ("status",),
    "depends_on": ("bergantung pada", "dependensi", "dependency"),
    "notes": ("catatan", "keterangan"),
}


def _key(header: str) -> str:
    return " ".join(header.split()).casefold()


DEFAULT_MAPPING = {
    _key(name): attribute
    for attribute in PROJECT_PLAN_FIELDS
    for name in (attribute, *_SYNONYMS[attribute])
}


class StructureError(ValueError):
    """Berkas tidak bisa dipakai sebagai Project Plan sama sekali."""


@dataclass
class RawTable:
    file_type: str  # "csv" atau "xlsx"
    header: list[str]
    # (nomor baris, sel) untuk setiap baris di bawah judul kolom, termasuk baris kosong.
    rows: list[tuple[int, list[str]]]
    sheet_name: str | None = None
    sheets: list[str] = field(default_factory=list)
    delimiter: str | None = None
    # Jumlah sel XLSX bertipe tanggal/angka/boolean per judul kolom.
    typed_cells: dict[str, int] = field(default_factory=dict)


@dataclass
class ProjectPlanRow:
    row_number: int
    # Atribut terpetakan -> sel apa adanya; None bila kolomnya tidak ada di berkas.
    values: dict[str, str | None]
    # Semua sel dengan judul kolom asli.
    raw: dict[str, Any]


@dataclass
class ProjectPlanParseResult:
    table: RawTable
    mapping: dict[str, str]  # judul kolom -> atribut
    unmapped_headers: list[str]
    missing_required: list[str]
    missing_optional: list[str]
    rows: list[ProjectPlanRow]
    skipped_blank_rows: list[int]
    # Masalah struktur. Bila ada, berkas tidak boleh diimpor.
    errors: list[str]

    @property
    def total_rows(self) -> int:
        return len(self.rows)


def read_table(data: bytes, file_name: str, sheet: str | None = None) -> RawTable:
    """Baca berkas menjadi judul kolom dan baris sel teks. StructureError bila tidak terbaca."""
    suffix = Path(file_name).suffix.lower()
    if not data:
        raise StructureError("Berkas kosong")
    if suffix == ".csv":
        return _read_csv(data)
    if suffix == ".xlsx":
        return _read_xlsx(data, sheet)
    raise StructureError("Berkas harus .csv atau .xlsx")


def _read_csv(data: bytes) -> RawTable:
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StructureError("Berkas CSV bukan UTF-8; simpan ulang sebagai CSV UTF-8") from exc
    first_line = content.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    try:
        records = list(csv.reader(io.StringIO(content, newline=""), delimiter=delimiter))
    except csv.Error as exc:
        raise StructureError(f"Berkas CSV tidak bisa dibaca: {exc}") from exc
    if not records:
        raise StructureError("Berkas kosong")
    rows = [(number, cells) for number, cells in enumerate(records[1:], start=2)]
    return RawTable("csv", records[0], rows, delimiter=delimiter)


def _cell(value: Any) -> tuple[str, bool]:
    """Teks sel XLSX dan apakah sel itu bertipe (bukan teks)."""
    if value is None:
        return "", False
    if isinstance(value, str):
        return value, False
    if isinstance(value, bool):
        return ("TRUE" if value else "FALSE"), True
    if isinstance(value, datetime):
        if value.time() == time(0, 0):
            return value.date().isoformat(), True
        return value.isoformat(sep=" "), True
    if isinstance(value, (date, time)):
        return value.isoformat(), True
    if isinstance(value, float):
        return (str(int(value)) if value.is_integer() else repr(value)), True
    return str(value), True


def _read_xlsx(data: bytes, sheet: str | None) -> RawTable:
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, InvalidFileException, KeyError, OSError, ValueError) as exc:
        raise StructureError("Berkas XLSX tidak bisa dibaca") from exc
    try:
        sheets = list(book.sheetnames)
        if sheet is not None and sheet not in sheets:
            raise StructureError(f"Sheet '{sheet}' tidak ada; pilihan: {', '.join(sheets)}")
        worksheet = book[sheet] if sheet is not None else book.worksheets[0]
        records = worksheet.iter_rows(values_only=True)
        first = next(records, None)
        if first is None:
            raise StructureError("Berkas kosong")
        header = [_cell(value)[0] for value in first]
        typed: Counter[str] = Counter()
        rows = []
        for number, values in enumerate(records, start=2):
            cells = []
            for index, value in enumerate(values):
                text, is_typed = _cell(value)
                if is_typed:
                    typed[header[index] if index < len(header) else EXTRA_KEY] += 1
                cells.append(text)
            rows.append((number, cells))
        return RawTable(
            "xlsx",
            header,
            rows,
            sheet_name=worksheet.title,
            sheets=sheets,
            typed_cells=dict(typed),
        )
    finally:
        book.close()


def _trim(cells: list[str]) -> list[str]:
    end = len(cells)
    while end and cells[end - 1].strip() == "":
        end -= 1
    return cells[:end]


def parse_project_plan(
    table: RawTable, column_map: dict[str, str | None] | None = None
) -> ProjectPlanParseResult:
    """Petakan kolom ke atribut staging dan ubah setiap baris menjadi ProjectPlanRow.

    `column_map` eksplisit `{judul kolom: atribut}` menimpa pemetaan bawaan; atribut `None`
    berarti kolom itu sengaja tidak dipetakan. Masalah struktur dikumpulkan di `errors`.
    """
    # Kolom kosong di ujung kanan (lebar sheet) diabaikan; yang di tengah diberi nama posisi.
    header = [
        name if name.strip() else f"(kolom {index + 1})"
        for index, name in enumerate(_trim(table.header))
    ]
    errors: list[str] = []
    if not header:
        errors.append("Baris judul kolom kosong")

    seen: dict[str, str] = {}
    for name in header:
        if _key(name) in seen:
            errors.append(f"Nama kolom ganda: '{seen[_key(name)]}' dan '{name}'")
        seen.setdefault(_key(name), name)

    explicit: dict[str, str | None] = {}
    for name, attribute in (column_map or {}).items():
        if _key(name) not in seen:
            errors.append(f"Kolom '{name}' pada pemetaan tidak ada di berkas")
        elif attribute is not None and attribute not in PROJECT_PLAN_FIELDS:
            errors.append(f"Atribut '{attribute}' tidak dikenal")
        else:
            explicit[_key(name)] = attribute

    mapping: dict[str, str] = {}
    source_of: dict[str, str] = {}
    for name in header:
        key = _key(name)
        attribute = explicit[key] if key in explicit else DEFAULT_MAPPING.get(key)
        if attribute is None:
            continue
        if attribute in source_of:
            errors.append(
                f"Atribut {attribute} dipetakan dari dua kolom: '{source_of[attribute]}' "
                f"dan '{name}'"
            )
            continue
        mapping[name] = attribute
        source_of[attribute] = name

    missing_required = [a for a in REQUIRED if a not in source_of]
    if missing_required:
        errors.append("Kolom wajib tidak ditemukan: " + ", ".join(missing_required))

    rows, blank = [], []
    for number, cells in table.rows:
        if all(cell.strip() == "" for cell in cells):
            blank.append(number)
            continue
        padded = cells + [""] * (len(header) - len(cells))
        raw: dict[str, Any] = dict(zip(header, padded))
        if extra := _trim(cells[len(header) :]):
            raw[EXTRA_KEY] = extra
        values = {
            attribute: (raw[source_of[attribute]] if attribute in source_of else None)
            for attribute in PROJECT_PLAN_FIELDS
        }
        rows.append(ProjectPlanRow(number, values, raw))

    if len(rows) > MAX_ROWS:
        errors.append(f"Berkas berisi {len(rows)} baris data, batasnya {MAX_ROWS}")

    return ProjectPlanParseResult(
        table=table,
        mapping=mapping,
        unmapped_headers=[name for name in header if name not in mapping],
        missing_required=missing_required,
        missing_optional=[
            a for a in PROJECT_PLAN_FIELDS if a not in source_of and a not in REQUIRED
        ],
        rows=rows,
        skipped_blank_rows=blank,
        errors=errors,
    )
