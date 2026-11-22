"""DIG-141: pembaca tanggal ketat per format sumber, termasuk setiap varian cacat format_tanggal
di generator data sintetis (synthetic/dirty.py)."""

from datetime import date

import pytest

from app.modules.data.quality.dates import ISO, PLAN, parse_date


@pytest.mark.parametrize(
    ("value", "fmt", "expected"),
    [
        ("2026-12-01", ISO, date(2026, 12, 1)),
        ("02/09/2026", PLAN, date(2026, 9, 2)),
        ("29/02/2028", PLAN, date(2028, 2, 29)),
    ],
)
def test_values_in_the_source_format_are_read(value, fmt, expected):
    assert parse_date(value, fmt) == expected


@pytest.mark.parametrize(
    "value",
    [
        "01/12/2026",  # final sources: %d/%m/%Y (PostgreSQL membacanya 12 Januari)
        "28 Sep 2026",  # final sources: %d %b %Y
        "2026/09/09",  # final sources: %Y/%m/%d
        "5 Okt 2026",
        "2026-9-1",
        " 2026-12-01",
        "2026-12-01T00:00:00",
        "2026-02-30",
        "",
        None,
    ],
)
def test_final_source_dates_must_be_iso(value):
    assert parse_date(value, ISO) is None


@pytest.mark.parametrize(
    "value",
    [
        "2026-11-03",  # Project Plan: ISO
        "9 Nov 2026",  # Project Plan: %d %b %Y tanpa nol di depan
        "11/9/26",  # Project Plan: d/m/yy
        "1/9/2026",
        "31/02/2026",
    ],
)
def test_project_plan_dates_must_be_dd_mm_yyyy(value):
    assert parse_date(value, PLAN) is None


def test_guessable_dates_are_still_rejected_in_the_rules():
    """Aturan 007 memakai pembaca yang sama: nilai yang bisa ditebak tetap pelanggaran."""
    from tests.test_quality_rules import CLEAN, found

    data = {**CLEAN, "tasks": [dict(row) for row in CLEAN["tasks"]]}
    data["tasks"][0]["planned_start"] = "2026/09/01"
    assert "DQ-TSK-007" in found(data)
    # Aturan turunan dilewati bila tanggalnya sendiri tidak terbaca.
    assert "DQ-TSK-009" not in found(data)
