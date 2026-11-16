"""DIG-140: adapter sasaran pemeriksaan (CSV, workbook, basis data)."""

import csv
from datetime import date, datetime

import pytest
from openpyxl import Workbook
from sqlalchemy import text

from app.modules.data.quality.rules import COLUMNS, validate_final_sources
from app.modules.data.quality.sources import as_text, read_csv_folder, read_database, read_workbook
from tests.conftest import REQUIRES_DB
from tests.test_quality_rules import CLEAN


def requires_db(test):
    for mark in REQUIRES_DB:
        test = mark(test)
    return test


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ""),
        (True, "true"),
        (False, "false"),
        (datetime(2026, 9, 1), "2026-09-01"),
        (datetime(2026, 9, 1, 8, 30), "2026-09-01T08:30:00"),
        (date(2026, 9, 1), "2026-09-01"),
        (1.0, "1"),
        (2.5, "2.5"),
        (3, "3"),
        ("Sari ", "Sari "),
    ],
)
def test_typed_cells_become_contract_text(value, expected):
    assert as_text(value) == expected


def write_csv(folder, table, rows):
    with (folder / f"{table}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, COLUMNS[table], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_csv_folder_keeps_text_and_row_numbers(tmp_path):
    for table, rows in CLEAN.items():
        write_csv(tmp_path, table, rows)
    tables = read_csv_folder(tmp_path)
    assert set(tables) == set(CLEAN)
    second = tables["tasks"][1]
    assert (second.number, second.key, second.values["estimated_days"]) == (3, "TSK-0002", "3.5")
    assert validate_final_sources(tables).findings == []


def test_missing_files_are_skipped_and_missing_columns_are_empty(tmp_path):
    (tmp_path / "tasks.csv").write_text("task_id,project_id\nTSK-0001,PRJ-001\n", encoding="utf-8")
    tables = read_csv_folder(tmp_path)
    assert list(tables) == ["tasks"]
    assert tables["tasks"][0].values["task_name"] == ""
    found = {f.rule_id for f in validate_final_sources(tables).findings}
    assert {"DQ-TSK-001", "DQ-TSK-004"} <= found  # project tidak dikenal: projects tidak ada


def test_workbook_sheets_with_csv_suffix_and_typed_cells(tmp_path):
    book = Workbook()
    sheet = book.active
    sheet.title = "holidays_csv"
    sheet.append(["holiday_date", "holiday_name"])
    sheet.append([datetime(2026, 8, 17), "Hari Kemerdekaan"])
    sheet.append([None, None])
    sheet.append(["17/08/2026", "Teks"])
    tasks = book.create_sheet("tasks")
    tasks.append(COLUMNS["tasks"])
    typed = {"priority_rank": 1.0, "estimated_days": 4.5, "dod_fulfilled": True}
    tasks.append([typed.get(c, CLEAN["tasks"][0][c]) for c in COLUMNS["tasks"]])
    book.save(tmp_path / "data.xlsx")

    tables = read_workbook(tmp_path / "data.xlsx")
    assert [(r.number, r.key) for r in tables["holidays"]] == [
        (2, "2026-08-17"),
        (4, "17/08/2026"),
    ]
    assert tables["holidays"][1].values["holiday_date"] == "17/08/2026"  # teks tetap apa adanya
    found = {f.rule_id for f in validate_final_sources(tables).findings}
    assert "DQ-HOL-007" in found
    task = tables["tasks"][0].values
    assert (task["priority_rank"], task["estimated_days"], task["dod_fulfilled"]) == (
        "1",
        "4.5",
        "true",
    )


@requires_db
def test_database_rows_use_the_same_text_form(client, db):
    db.execute(
        text(
            "INSERT INTO projects (project_id, project_name, process_owner, priority_rank, "
            "start_date, target_launch_date, status, dor_fulfilled) VALUES "
            "('PRJ-001', 'Presensi', 'Biro SDM', 1, '2026-09-01', '2026-12-01', "
            "'development', false)"
        )
    )
    db.commit()
    tables = read_database(db)
    assert set(tables) == set(CLEAN)
    project = tables["projects"][0]
    assert (project.number, project.key) == (None, "PRJ-001")
    assert project.values["start_date"] == "2026-09-01"
    assert project.values["dor_fulfilled"] == "false"
    assert project.values["actual_launch_date"] == ""
    assert tables["roles"]  # seed migrasi
    assert not [f for f in validate_final_sources(tables).findings if f.level == "tolak"]
