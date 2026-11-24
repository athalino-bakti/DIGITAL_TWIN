"""DIG-162: aturan impor terhadap perubahan manual, tanpa basis data."""

from datetime import date, datetime

from app.modules.data.enums import TaskStatus
from app.modules.data.manual_change import OpenChange, merge_task_import, to_text


def change(field, new_value, ids=(1,)):
    return OpenChange(field, new_value, ids, datetime(2026, 11, 16, 9, 0), 7, "status_update")


def test_to_text_normalizes_types():
    assert to_text(None) is None
    assert to_text(True) == "true"
    assert to_text(False) == "false"
    assert to_text(TaskStatus.IN_QA) == "in_qa"
    assert to_text(date(2026, 3, 6)) == "2026-03-06"
    assert to_text(3) == "3"


def test_fields_without_manual_change_are_overwritten():
    result = merge_task_import(
        {"status": "in_progress", "priority_rank": 2},
        {"status": "done", "priority_rank": 2},
        {},
    )
    assert result.updates == {"status": "done"}  # yang sama tidak perlu ditulis ulang
    assert (result.conflicts, result.caught_up) == ([], [])


def test_manual_change_is_not_overwritten_and_reported():
    pending = {"status": change("status", "on_hold")}
    result = merge_task_import({"status": "on_hold"}, {"status": "in_progress"}, pending)
    assert result.updates == {}
    [conflict] = result.conflicts
    assert (conflict.field, conflict.current, conflict.incoming) == (
        "status",
        "on_hold",
        "in_progress",
    )
    assert conflict.change.changed_by == 7


def test_source_that_caught_up_closes_the_change():
    pending = {"priority_rank": change("priority_rank", "5", ids=(3, 4))}
    result = merge_task_import({"priority_rank": 5}, {"priority_rank": 5}, pending)
    assert (result.updates, result.conflicts) == ({}, [])
    assert result.caught_up == [3, 4]


def test_mixed_fields_and_types():
    pending = {"status": change("status", "blocked")}
    result = merge_task_import(
        {"status": TaskStatus.BLOCKED, "actual_finish": None, "dod_fulfilled": False},
        {"status": "done", "actual_finish": date(2026, 3, 9), "dod_fulfilled": False},
        pending,
    )
    assert result.updates == {"actual_finish": date(2026, 3, 9)}
    assert [c.field for c in result.conflicts] == ["status"]


def test_columns_only_in_incoming_are_passed_through():
    result = merge_task_import({}, {"task_name": "Form cuti"}, {})
    assert result.updates == {"task_name": "Form cuti"}
