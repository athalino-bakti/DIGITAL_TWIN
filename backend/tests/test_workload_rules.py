"""DIG-138: aturan tanggal dan hotfix D-08, serta pembacaan CSV impor. Tanpa basis data."""

from datetime import date

import pytest

from app.modules.data.workload_service import CSV_COLUMNS, check_workload_rules, parse_workload_csv

RELEASED = {"PRJ-001": date(2026, 9, 1)}
NOT_RELEASED = {"PRJ-002": None}
PROJECTS = RELEASED | NOT_RELEASED


def item(**overrides) -> dict:
    return {
        "item_type": "ticket",
        "related_project_id": None,
        "received_date": date(2026, 10, 5),
        "started_date": None,
        "resolved_date": None,
        "is_hotfix": False,
    } | overrides


def fields(values: dict, projects: dict = PROJECTS) -> list[str]:
    return [error.field for error in check_workload_rules(values, projects)]


# --- aturan tanggal ---


def test_valid_item_without_dates_has_no_errors():
    assert fields(item()) == []


def test_dates_on_same_day_are_valid():
    day = date(2026, 10, 5)
    assert fields(item(started_date=day, resolved_date=day)) == []


def test_started_before_received():
    assert fields(item(started_date=date(2026, 10, 4))) == ["started_date"]


def test_resolved_before_received():
    assert fields(item(resolved_date=date(2026, 10, 4))) == ["resolved_date"]


def test_resolved_before_started():
    values = item(started_date=date(2026, 10, 7), resolved_date=date(2026, 10, 6))
    assert fields(values) == ["resolved_date"]


def test_resolved_without_started_is_allowed():
    """Sama dengan constraint DB: started_date boleh kosong walau sudah selesai."""
    assert fields(item(resolved_date=date(2026, 10, 6))) == []


def test_unknown_project():
    assert fields(item(related_project_id="PRJ-404")) == ["related_project_id"]


# --- aturan hotfix ---


def test_hotfix_ticket_on_released_app_is_valid():
    assert fields(item(is_hotfix=True, related_project_id="PRJ-001")) == []


def test_hotfix_received_on_launch_day_is_valid():
    values = item(is_hotfix=True, related_project_id="PRJ-001", received_date=date(2026, 9, 1))
    assert fields(values) == []


def test_hotfix_must_be_ticket():
    values = item(is_hotfix=True, item_type="operational", related_project_id="PRJ-001")
    assert fields(values) == ["is_hotfix"]


def test_hotfix_needs_project():
    assert fields(item(is_hotfix=True)) == ["related_project_id"]


def test_hotfix_on_unreleased_app():
    errors = check_workload_rules(item(is_hotfix=True, related_project_id="PRJ-002"), PROJECTS)
    assert [(e.field, e.error_type) for e in errors] == [
        ("related_project_id", "hotfix_needs_release")
    ]
    assert "belum rilis" in errors[0].message


def test_hotfix_received_before_launch():
    values = item(is_hotfix=True, related_project_id="PRJ-001", received_date=date(2026, 8, 31))
    errors = check_workload_rules(values, PROJECTS)
    assert [e.error_type for e in errors] == ["hotfix_needs_release"]
    assert "2026-09-01" in errors[0].message


def test_operational_hotfix_without_project_reports_both():
    assert fields(item(is_hotfix=True, item_type="operational")) == [
        "is_hotfix",
        "related_project_id",
    ]


def test_non_hotfix_ticket_may_reference_unreleased_project():
    assert fields(item(related_project_id="PRJ-002")) == []


# --- pembacaan CSV ---

HEADER = ",".join(CSV_COLUMNS)


def csv(*lines: str, header: str = HEADER) -> str:
    return "\n".join([header, *lines]) + "\n"


def test_parse_valid_rows_with_empty_cells_as_null():
    rows, errors, total = parse_workload_csv(
        csv(
            "WLI-0001,RES-001,ticket,PRJ-001,2026-10-05,2026-10-06,,high,false",
            ",RES-002,operational,,2026-10-07,,,,TRUE",
        )
    )
    assert errors == []
    assert total == 2
    assert [line for line, _ in rows] == [2, 3]
    first, second = rows[0][1], rows[1][1]
    assert first["started_date"] == date(2026, 10, 6)
    assert first["resolved_date"] is None
    assert second["item_id"] is None
    assert second["severity"] is None
    assert second["is_hotfix"] is True


def test_parse_accepts_bom_crlf_and_any_column_order():
    header = ",".join(reversed(CSV_COLUMNS))
    content = "﻿" + header + "\r\nfalse,low,,,2026-10-05,,operational,RES-001,WLI-0001\r\n"
    rows, errors, total = parse_workload_csv(content)
    assert (errors, total) == ([], 1)
    assert rows[0][1]["item_id"] == "WLI-0001"


def test_parse_skips_blank_lines():
    rows, errors, total = parse_workload_csv(
        csv("WLI-0001,RES-001,ticket,,2026-10-05,,,,false", ",,,,,,,,", "")
    )
    assert (len(rows), errors, total) == (1, [], 1)


@pytest.mark.parametrize(
    "header,expected",
    [
        ("item_id,resource_id", "kolom hilang"),
        (HEADER + ",catatan", "kolom tidak dikenal: catatan"),
        ("", "Berkas kosong"),
    ],
)
def test_parse_rejects_wrong_header(header, expected):
    rows, errors, total = parse_workload_csv(header + "\n")
    assert rows == [] and total == 0
    assert [e.row for e in errors] == [1]
    assert expected in errors[0].message


@pytest.mark.parametrize(
    "line,field,message",
    [
        ("WLI-1,RES-001,ticket,,2026-10-05,,,,false", "item_id", "WLI-0001"),
        ("WLI-0001,RES-001,tiket,,2026-10-05,,,,false", "item_type", "operational atau ticket"),
        ("WLI-0001,RES-001,ticket,,05/10/2026,,,,false", "received_date", "YYYY-MM-DD"),
        ("WLI-0001,RES-001,ticket,,2026-10-05,,,urgent,false", "severity", "critical"),
        ("WLI-0001,RES-001,ticket,,2026-10-05,,,,ya", "is_hotfix", "true atau false"),
        ("WLI-0001,,ticket,,2026-10-05,,,,false", "resource_id", "Wajib diisi"),
        ("WLI-0001,RES-001,ticket,,2026-10-05,,,,", "is_hotfix", "true atau false"),
    ],
)
def test_parse_reports_cell_errors_with_row_number(line, field, message):
    rows, errors, total = parse_workload_csv(
        csv("WLI-0002,RES-001,ticket,,2026-10-05,,,,false", line)
    )
    assert total == 2
    assert [line for line, _ in rows] == [2]
    assert [(e.row, e.field) for e in errors] == [(3, field)]
    assert message in errors[0].message
    assert errors[0].item_id == (line.split(",")[0] or None)


def test_parse_rejects_extra_cells():
    rows, errors, _ = parse_workload_csv(csv("WLI-0001,RES-001,ticket,,2026-10-05,,,,false,lebih"))
    assert rows == []
    assert errors[0].message == "Jumlah kolom melebihi judul"
