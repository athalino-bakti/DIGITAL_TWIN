"""DIG-180: perhitungan keterlambatan task untuk Gantt. Tanpa basis data."""

from datetime import date

import pytest

from app.modules.digital_twin.timeline_service import NOT_LATE, task_delay

# Jumat 6 Maret 2026 sebagai planned_finish; Senin 9 Maret hari kerja berikutnya.
PLANNED = date(2026, 3, 6)
AS_OF = date(2026, 3, 20)


def test_done_on_time_or_early_is_not_late():
    assert task_delay("done", PLANNED, PLANNED, AS_OF) == NOT_LATE
    assert task_delay("done", PLANNED, date(2026, 3, 4), AS_OF) == NOT_LATE


def test_done_late_counts_from_day_after_planned_finish():
    # Selesai Selasa 10 Maret: 4 hari kalender, 2 hari kerja (Senin, Selasa).
    assert task_delay("done", PLANNED, date(2026, 3, 10), AS_OF) == (True, 4, 2)


def test_done_on_weekend_is_late_with_zero_working_days():
    """Pola dataset dosbim: tanggal bisa jatuh di akhir pekan."""
    assert task_delay("done", PLANNED, date(2026, 3, 7), AS_OF) == (True, 1, 0)


def test_holidays_do_not_count_as_working_days():
    holidays = {date(2026, 3, 9)}
    assert task_delay("done", PLANNED, date(2026, 3, 10), AS_OF, holidays) == (True, 4, 1)


def test_done_task_ignores_as_of():
    late = task_delay("done", PLANNED, date(2026, 3, 10), date(2026, 12, 31))
    assert late == (True, 4, 2)


@pytest.mark.parametrize("status", ["not_started", "in_progress", "blocked", "on_hold", "in_qa"])
def test_open_task_is_late_after_planned_finish(status):
    assert task_delay(status, PLANNED, None, PLANNED) == NOT_LATE
    assert task_delay(status, PLANNED, None, date(2026, 3, 5)) == NOT_LATE
    # 20 Maret: 14 hari kalender, 10 hari kerja.
    assert task_delay(status, PLANNED, None, AS_OF) == (True, 14, 10)


def test_dropped_task_is_never_late():
    assert task_delay("dropped", PLANNED, None, AS_OF) == NOT_LATE


def test_done_without_actual_finish_falls_back_to_as_of():
    assert task_delay("done", PLANNED, None, AS_OF) == (True, 14, 10)


def test_planned_finish_on_weekend():
    saturday = date(2026, 3, 7)
    assert task_delay("in_progress", saturday, None, date(2026, 3, 8)) == (True, 1, 0)
    assert task_delay("in_progress", saturday, None, date(2026, 3, 9)) == (True, 2, 1)
