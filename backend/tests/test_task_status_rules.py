"""DIG-161: aturan status, tanggal aktual, dan DoD task (D-05). Tanpa basis data."""

from datetime import date

import pytest

from app.modules.data.task_service import check_task_status_rules

START, FINISH = date(2026, 3, 2), date(2026, 3, 6)


def fields(status, start=None, finish=None, dod=False) -> list[str]:
    values = {
        "status": status,
        "actual_start": start,
        "actual_finish": finish,
        "dod_fulfilled": dod,
    }
    return [e.field for e in check_task_status_rules(values)]


@pytest.mark.parametrize(
    "status,start,finish,dod",
    [
        ("not_started", None, None, False),
        ("in_progress", START, None, False),
        ("blocked", START, None, False),
        ("in_qa", START, None, False),
        ("on_hold", None, None, False),
        ("on_hold", START, None, False),
        ("dropped", None, None, False),
        ("dropped", START, None, False),
        ("done", START, FINISH, True),
        ("done", START, FINISH, False),
        ("done", START, START, True),
    ],
)
def test_patterns_from_dosbim_dataset_are_valid(status, start, finish, dod):
    assert fields(status, start, finish, dod) == []


def test_not_started_has_no_actual_dates():
    assert fields("not_started", START) == ["actual_start"]


@pytest.mark.parametrize("status", ["in_progress", "blocked", "in_qa"])
def test_working_statuses_need_start(status):
    assert fields(status) == ["actual_start"]


@pytest.mark.parametrize("status", ["in_progress", "blocked", "in_qa", "on_hold", "dropped"])
def test_only_done_has_finish(status):
    assert "actual_finish" in fields(status, START, FINISH)


def test_done_needs_both_dates():
    assert fields("done") == ["actual_start", "actual_finish"]
    assert fields("done", START) == ["actual_finish"]


def test_finish_before_start():
    assert fields("done", FINISH, START) == ["actual_finish"]


@pytest.mark.parametrize("status", ["in_progress", "in_qa", "on_hold"])
def test_dod_only_for_done(status):
    assert fields(status, START, dod=True) == ["dod_fulfilled"]
