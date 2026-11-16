"""DIG-175: proyeksi selesai proyek untuk kartu "Proyek lewat target", tanpa basis data."""

from datetime import date

import pytest

from app.modules.digital_twin.summary_service import projected_finish, task_end

AS_OF = date(2026, 3, 16)


@pytest.mark.parametrize(
    ("status", "planned", "actual", "expected"),
    [
        ("done", date(2026, 3, 6), date(2026, 3, 9), date(2026, 3, 9)),  # pakai actual_finish
        ("done", date(2026, 3, 6), None, date(2026, 3, 6)),
        ("in_progress", date(2026, 3, 30), None, date(2026, 3, 30)),  # belum jatuh tempo
        ("in_progress", date(2026, 3, 6), None, AS_OF),  # lewat rencana: paling cepat hari ini
        ("blocked", date(2026, 3, 6), None, AS_OF),
        ("not_started", date(2026, 3, 16), None, AS_OF),
    ],
)
def test_task_end(status, planned, actual, expected):
    assert task_end(status, planned, actual, AS_OF) == expected


def test_projected_finish_ignores_dropped_and_takes_latest():
    tasks = [
        ("done", date(2026, 3, 6), date(2026, 3, 9)),
        ("dropped", date(2026, 12, 31), None),
        ("in_qa", date(2026, 3, 20), None),
    ]
    assert projected_finish(tasks, AS_OF) == date(2026, 3, 20)


def test_projected_finish_without_tasks():
    assert projected_finish([], AS_OF) is None
    assert projected_finish([("dropped", date(2026, 3, 1), None)], AS_OF) is None
