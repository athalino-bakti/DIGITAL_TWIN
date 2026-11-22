"""DIG-116: parser Project Plan CSV/XLSX (DIG-114), tanpa basis data.

Fixture dipangkas dari keluaran generator data sintetis J&C (seed 42, as-of 2026-11-06):
`project_plan_bersih_PRJ-002.csv` dari `raw/`, `project_plan_kotor_PRJ-002.csv` dari `dirty/raw/`.
Isinya baris PRJ-002 yang terkena cacat di `manifest_cacat.csv`, ditambah satu baris PRJ-003
(TSK-0089) yang membawa cacat `fk_tidak_dikenal`.
"""

import csv
import io
from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.integrations.project_plan import parser
from app.integrations.project_plan.parser import (
    EXTRA_KEY,
    StructureError,
    parse_project_plan,
    read_table,
)
from app.modules.data.staging_models import PROJECT_PLAN_FIELDS

FIXTURES = Path(__file__).parent / "fixtures"
CLEAN = FIXTURES / "project_plan_bersih_PRJ-002.csv"
DIRTY = FIXTURES / "project_plan_kotor_PRJ-002.csv"
DATE_FIELDS = ("planned_start", "planned_finish", "actual_start", "actual_finish")

# (Kode, atribut, nilai kotor) dari manifest_cacat.csv bersumber project_plan.
DEFECTS = [
    ("TSK-0064", "planned_start", "2026-11-03"),  # format_tanggal
    ("TSK-0107", "planned_start", "9 Nov 2026"),  # format_tanggal
    ("TSK-0049", "planned_start", "11/9/26"),  # format_tanggal
    ("TSK-0062", "pic", "RIZKY RAMADHAN"),  # alias_berbeda
    ("TSK-0057", "pic", "yoga p"),  # alias_berbeda
    ("TSK-0061", "estimated_days", ""),  # wajib_kosong
    ("TSK-0041", "depends_on", "TSK-0042 (hard)"),  # siklus_dependency
    ("TSK-0089", "pic", "Dodi (magang)"),  # fk_tidak_dikenal
]


def parse_file(path: Path, **kwargs):
    return parse_project_plan(read_table(path.read_bytes(), path.name), **kwargs)


def parse_text(content: str, name: str = "plan.csv", **kwargs):
    return parse_project_plan(read_table(content.encode("utf-8"), name), **kwargs)


def by_code(result) -> dict[str, list]:
    rows: dict[str, list] = {}
    for row in result.rows:
        rows.setdefault(row.values["task_code"], []).append(row)
    return rows


# --- nilai apa adanya ------------------------------------------------------------------------


@pytest.mark.parametrize(("code", "attribute", "value"), DEFECTS)
def test_dirty_values_reach_staging_unchanged(code, attribute, value):
    result = parse_file(DIRTY)
    assert result.errors == []
    assert by_code(result)[code][0].values[attribute] == value


def test_duplicate_rows_are_kept_with_their_own_row_number():
    result = parse_file(DIRTY)
    copies = by_code(result)["TSK-0046"]
    assert [row.row_number for row in copies] == [4, 11]
    assert copies[0].values == copies[1].values
    assert result.total_rows == 11
    assert parse_file(CLEAN).total_rows == 10


def test_every_cell_is_kept_in_raw_with_original_headers():
    first = parse_file(CLEAN).rows[0]
    assert first.row_number == 2
    assert first.raw["No"] == "1"
    assert first.raw["Kode"] == "TSK-0041"
    assert first.raw["Estimasi (hari)"] == first.values["estimated_days"] == "7"
    assert set(PROJECT_PLAN_FIELDS) == set(first.values)


def test_cells_are_not_stripped_and_blank_rows_are_skipped():
    result = parse_text("Kode,Task,Catatan\n TSK-0001 ,Analisis,\n,,\n\nTSK-0002,Uji, catatan \n")
    assert [row.row_number for row in result.rows] == [2, 5]
    assert result.skipped_blank_rows == [3, 4]
    assert result.rows[0].values["task_code"] == " TSK-0001 "
    assert result.rows[0].values["notes"] == ""
    assert result.rows[1].values["notes"] == " catatan "
    # Kolom yang tidak ada di berkas menjadi None, bukan "".
    assert result.rows[0].values["pic"] is None


def test_short_and_long_rows():
    result = parse_text("Kode,Task,PIC\nTSK-0001\nTSK-0002,Uji,Sari,lebih,\n")
    short, long = result.rows
    assert (short.values["task_name"], short.values["pic"]) == ("", "")
    assert long.raw[EXTRA_KEY] == ["lebih"]
    assert EXTRA_KEY not in short.raw


def test_multiline_cell_counts_as_one_row():
    result = parse_text('Kode,Task\nTSK-0001,"baris satu\nbaris dua"\nTSK-0002,Uji\n')
    assert [row.row_number for row in result.rows] == [2, 3]
    assert result.rows[0].values["task_name"] == "baris satu\nbaris dua"


# --- format CSV ------------------------------------------------------------------------------


def test_semicolon_csv_with_bom_gives_the_same_rows():
    comma = parse_file(CLEAN)
    content = CLEAN.read_text(encoding="utf-8")
    records = list(csv.reader(io.StringIO(content, newline="")))
    out = io.StringIO()
    csv.writer(out, delimiter=";", lineterminator="\r\n").writerows(records)
    data = "﻿".encode() + out.getvalue().encode("utf-8")

    table = read_table(data, "plan.csv")
    semicolon = parse_project_plan(table)
    assert table.delimiter == ";"
    assert table.header[0] == "No"  # BOM tidak ikut menjadi nama kolom
    assert [r.values for r in semicolon.rows] == [r.values for r in comma.rows]


def test_csv_that_is_not_utf8_is_rejected():
    with pytest.raises(StructureError, match="UTF-8"):
        read_table("Kode,Task\nTSK-0001,Pengujian ½\n".encode("cp1252"), "plan.csv")


@pytest.mark.parametrize(("data", "name"), [(b"", "plan.csv"), (b"abc", "plan.txt")])
def test_empty_or_unknown_files_are_rejected(data, name):
    with pytest.raises(StructureError):
        read_table(data, name)


# --- XLSX ------------------------------------------------------------------------------------


def to_date(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def xlsx_from_csv(path: Path, blank_row_after: int | None = None) -> bytes:
    """Salin fixture CSV ke XLSX: tanggal sebagai sel tanggal, prioritas dan estimasi angka."""
    with path.open(encoding="utf-8", newline="") as handle:
        header, *rows = list(csv.reader(handle))
    book = Workbook()
    sheet = book.active
    sheet.title = "Plan"
    sheet.append(header)
    for index, cells in enumerate(rows):
        typed = []
        for name, cell in zip(header, cells):
            if name in ("Mulai Rencana", "Selesai Rencana", "Mulai Aktual", "Selesai Aktual"):
                typed.append(to_date(cell) if cell else None)
            elif name in ("No", "Prioritas"):
                typed.append(int(cell))
            elif name == "Estimasi (hari)":
                typed.append(float(cell.replace(",", ".")) if cell else None)
            else:
                typed.append(cell or None)
        sheet.append(typed)
        if index == blank_row_after:
            sheet.append([])
    book.create_sheet("Catatan").append(["bukan project plan"])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_xlsx_matches_csv_in_meaning():
    csv_rows = parse_file(CLEAN).rows
    table = read_table(xlsx_from_csv(CLEAN), "project_plan_PRJ-002.xlsx")
    result = parse_project_plan(table)

    assert result.errors == []
    assert (table.file_type, table.sheet_name, table.sheets) == (
        "xlsx",
        "Plan",
        ["Plan", "Catatan"],
    )
    assert len(result.rows) == len(csv_rows)
    for from_csv, from_xlsx in zip(csv_rows, result.rows):
        assert from_xlsx.row_number == from_csv.row_number
        for attribute, value in from_csv.values.items():
            stored = from_xlsx.values[attribute]
            if attribute in DATE_FIELDS and value:
                assert stored == to_date(value).isoformat()
            elif attribute == "estimated_days":
                assert float(stored) == float(value.replace(",", "."))
            else:
                assert stored == value, attribute
    assert table.typed_cells["Mulai Rencana"] == len(csv_rows)
    assert table.typed_cells["Prioritas"] == len(csv_rows)
    assert "Task" not in table.typed_cells


def test_xlsx_numbers_and_blank_rows():
    table = read_table(xlsx_from_csv(CLEAN, blank_row_after=0), "plan.xlsx")
    result = parse_project_plan(table)
    estimates = {row.values["task_code"]: row.values["estimated_days"] for row in result.rows}
    assert estimates["TSK-0041"] == "7"  # bilangan bulat tanpa ".0"
    assert estimates["TSK-0046"] == "5.5"
    assert result.skipped_blank_rows == [3]
    assert [row.row_number for row in result.rows][:2] == [2, 4]


def test_xlsx_sheet_can_be_chosen():
    data = xlsx_from_csv(CLEAN)
    other = read_table(data, "plan.xlsx", sheet="Catatan")
    assert other.sheet_name == "Catatan"
    assert parse_project_plan(other).missing_required == ["task_code", "task_name"]
    with pytest.raises(StructureError, match="Sheet 'Tidak Ada' tidak ada"):
        read_table(data, "plan.xlsx", sheet="Tidak Ada")


def test_broken_xlsx_is_rejected():
    with pytest.raises(StructureError, match="XLSX"):
        read_table(b"PK\x03\x04 bukan zip", "plan.xlsx")


# --- pemetaan kolom --------------------------------------------------------------------------


def test_default_mapping_follows_the_template():
    result = parse_file(CLEAN)
    assert result.mapping["Kode"] == "task_code"
    assert result.mapping["Bergantung Pada"] == "depends_on"
    assert result.unmapped_headers == ["No"]
    assert result.missing_required == result.missing_optional == []


def test_synonyms_ignore_case_and_outer_spaces():
    result = parse_text("  KODE TASK ,nama task,Planned_Start,Keterangan\nTSK-0001,Uji,1/1/26,x\n")
    assert result.errors == []
    assert result.mapping == {
        "  KODE TASK ": "task_code",
        "nama task": "task_name",
        "Planned_Start": "planned_start",
        "Keterangan": "notes",
    }
    assert "pic" in result.missing_optional


def test_explicit_mapping_overrides_the_default():
    content = "ID,Kode,Judul,Task\nTSK-0001,lama,Analisis,abaikan\n"
    result = parse_text(
        content,
        column_map={"id": "task_code", "Kode": None, "Judul": "task_name", "Task": None},
    )
    assert result.errors == []
    assert result.mapping == {"ID": "task_code", "Judul": "task_name"}
    assert result.unmapped_headers == ["Kode", "Task"]
    assert result.rows[0].values["task_code"] == "TSK-0001"
    assert result.rows[0].raw["Kode"] == "lama"


@pytest.mark.parametrize(
    ("content", "column_map", "message"),
    [
        ("Fitur,Catatan\nA,B\n", None, "Kolom wajib tidak ditemukan: task_code, task_name"),
        ("Kode,Task\nTSK-0001,A\n", {"Kode": "kode_task"}, "Atribut 'kode_task' tidak dikenal"),
        ("Kode,Task\nTSK-0001,A\n", {"PIC": "pic"}, "Kolom 'PIC' pada pemetaan tidak ada"),
        ("Kode,Task,kode\nTSK-0001,A,B\n", None, "Nama kolom ganda"),
        ("Kode,Task,ID\nTSK-0001,A,B\n", {"ID": "task_code"}, "dipetakan dari dua kolom"),
        ("\n", None, "Baris judul kolom kosong"),
    ],
)
def test_structure_problems_are_reported(content, column_map, message):
    result = parse_text(content, column_map=column_map)
    assert any(message in error for error in result.errors), result.errors


def test_row_limit(monkeypatch):
    monkeypatch.setattr(parser, "MAX_ROWS", 2)
    result = parse_text("Kode,Task\nTSK-1,A\nTSK-2,B\nTSK-3,C\n")
    assert result.errors == ["Berkas berisi 3 baris data, batasnya 2"]
