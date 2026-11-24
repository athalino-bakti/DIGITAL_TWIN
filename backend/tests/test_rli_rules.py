"""DIG-190: formula Resource Load Index (DIG-187) dengan data sintetis, tanpa basis data."""

from datetime import date, timedelta

import pytest

from app.modules.data.models import Assignment, Task, WorkloadItem
from app.modules.digital_twin import rli_config as cfg
from app.modules.digital_twin.rli import (
    Inputs,
    Load,
    Member,
    category,
    compute_cell,
    item_load,
    onboarding_factor,
    task_load,
)

MON = date(2026, 3, 2)
FRI = MON + timedelta(days=4)
WEEK = (MON, FRI)
VETERAN = date(2024, 1, 1)


def member(join=VETERAN, capacity=3.0) -> Member:
    return Member("RES-001", "Anggota Sintetis", "ROLE-BE", capacity, join)


def full_week(weight: float) -> Load:
    return Load(weight, (WEEK,))


def cell(loads=(), items=(), absences=(), holidays=(), join=VETERAN, capacity=3.0):
    inputs = Inputs([member(join, capacity)], holidays=set(holidays))
    inputs.tasks["RES-001"] = list(loads)
    inputs.items["RES-001"] = list(items)
    inputs.absences["RES-001"] = list(absences)
    return compute_cell(member(join, capacity), MON, inputs)


def test_week_starts_on_monday():
    assert MON.weekday() == 0


def test_example_from_the_proposal():
    """USULAN_FORMULA_RLI.md bagian 4: CX-H + CX-M penuh, tiket high 2 hari, cuti 1 hari."""
    ticket = Load(0.6, ((MON, MON + timedelta(days=1)),))
    leave = [(FRI, FRI)]
    result = cell([full_week(1.2), full_week(0.9)], [ticket], leave)
    assert (result.project_load, result.non_project_load) == (2.1, 0.24)
    assert (result.capacity, result.available_days) == (2.4, 4)
    assert (result.rli, result.category) == (0.975, "penuh")
    assert (result.tasks, result.workload_items) == (2, 1)

    heavier = cell([full_week(1.2), full_week(0.9), full_week(0.9)], [ticket], leave)
    assert (heavier.rli, heavier.category) == (1.35, "overload_berat")


def test_week_without_working_days_is_skipped():
    holidays = [MON + timedelta(days=i) for i in range(5)]
    result = cell([full_week(1.2)], holidays=holidays)
    assert (result.rli, result.category, result.available_days) == (None, cfg.UNAVAILABLE, 0)
    assert (result.project_load, result.tasks) == (0.0, 0)


def test_holiday_shortens_the_week_for_load_and_capacity():
    result = cell([full_week(1.5)], holidays=[MON])
    # 4 hari kerja: beban penuh minggu tetap 1,5, kapasitas tetap 3,0 karena hadir semua.
    assert (result.project_load, result.capacity, result.rli) == (1.5, 3.0, 0.5)


def test_overlapping_absences_are_not_counted_twice():
    absences = [(MON, MON + timedelta(days=2)), (MON + timedelta(days=1), MON + timedelta(days=3))]
    result = cell([full_week(0.6)], absences=absences)
    assert result.available_days == 1
    assert result.capacity == 0.6


def test_absence_on_a_holiday_is_not_counted_twice():
    result = cell([full_week(0.6)], absences=[(MON, MON)], holidays=[MON])
    assert result.available_days == 4


def test_partial_week_assignment_is_proportional():
    wednesday = MON + timedelta(days=2)
    result = cell([Load(1.5, ((wednesday, date.max), WEEK))])
    assert result.project_load == pytest.approx(1.5 * 3 / 5)


def test_assignment_and_task_window_must_overlap():
    tuesday, thursday = MON + timedelta(days=1), MON + timedelta(days=3)
    # Ditugaskan sejak Selasa, task baru mulai Kamis: hanya Kamis dan Jumat yang aktif.
    result = cell([Load(1.0, ((tuesday, date.max), (thursday, FRI)))])
    assert result.project_load == 0.4


def task(status, planned=(MON, FRI), actual=(None, None)) -> Task:
    return Task(
        task_id="TSK-0001",
        project_id="PRJ-001",
        status=status,
        planned_start=planned[0],
        planned_finish=planned[1],
        actual_start=actual[0],
        actual_finish=actual[1],
    )


def held(assigned=MON, released=None) -> Assignment:
    return Assignment(assigned_date=assigned, released_date=released)


@pytest.mark.parametrize("status", ["dropped", "on_hold"])
def test_dropped_and_on_hold_tasks_add_no_load(status):
    assert task_load(held(), task(status), 0.9, as_of=FRI) is None


@pytest.mark.parametrize("status", ["not_started", "in_progress", "blocked", "in_qa", "done"])
def test_other_task_statuses_add_load(status):
    load = task_load(held(), task(status), 0.9, as_of=FRI)
    assert cell([load]).project_load == 0.9


def test_open_task_past_its_plan_runs_until_as_of():
    late = task("in_progress", planned=(MON - timedelta(days=14), MON - timedelta(days=7)))
    load = task_load(held(MON - timedelta(days=14)), late, 1.2, as_of=MON + timedelta(days=1))
    assert cell([load]).project_load == pytest.approx(1.2 * 2 / 5)


def test_released_assignment_stops_adding_load():
    load = task_load(held(released=MON + timedelta(days=1)), task("in_progress"), 1.0, as_of=FRI)
    assert cell([load]).project_load == 0.4


@pytest.mark.parametrize(
    ("item_type", "severity", "hotfix", "weight"),
    [
        ("operational", None, False, 0.3),
        ("ticket", "low", False, 0.2),
        ("ticket", "medium", False, 0.4),
        ("ticket", None, False, 0.4),
        ("ticket", "high", False, 0.6),
        ("ticket", "critical", False, 1.0),
        ("ticket", "low", True, 1.0),
    ],
)
def test_workload_item_weight(item_type, severity, hotfix, weight):
    item = WorkloadItem(
        item_type=item_type,
        severity=severity,
        is_hotfix=hotfix,
        received_date=MON,
        started_date=None,
        resolved_date=None,
    )
    load = item_load(item, as_of=FRI)
    assert load.weight == weight
    assert cell(items=[load]).non_project_load == weight


@pytest.mark.parametrize(
    ("days", "factor"), [(0, 0.5), (30, 0.5), (31, 0.75), (90, 0.75), (91, 1.0), (-3, 0.5)]
)
def test_onboarding_thresholds(days, factor):
    assert onboarding_factor(MON - timedelta(days=days), MON) == factor


def test_onboarding_reduces_capacity():
    result = cell([full_week(1.5)], join=MON - timedelta(days=60))
    assert (result.onboarding_factor, result.capacity, result.rli) == (0.75, 2.25, 0.667)


def test_days_before_join_date_are_unavailable():
    wednesday = MON + timedelta(days=2)
    result = cell([Load(0.9, ((wednesday, date.max), WEEK))], join=wednesday)
    assert result.available_days == 3
    assert result.capacity == pytest.approx(3.0 * 3 / 5 * 0.5)


@pytest.mark.parametrize(
    ("rli", "code"),
    [
        (0.0, "rendah"),
        (0.499, "rendah"),
        (0.5, "sedang"),
        (0.799, "sedang"),
        (0.8, "penuh"),
        (1.0, "penuh"),
        (1.001, "overload"),
        (1.2, "overload"),
        (1.201, "overload_berat"),
        (None, cfg.UNAVAILABLE),
    ],
)
def test_category_boundaries(rli, code):
    assert category(rli) == code


def test_float_noise_does_not_cross_a_boundary():
    # 2,4 / 3,0 di float adalah 0,7999...; setelah dibulatkan tetap "penuh".
    result = cell([full_week(2.4)])
    assert (result.rli, result.category) == (0.8, "penuh")


def test_fully_unavailable_member_keeps_its_load_visible():
    result = cell([full_week(0.9)], absences=[WEEK])
    assert (result.rli, result.category, result.capacity) == (None, cfg.UNAVAILABLE, 0.0)
    assert (result.project_load, result.tasks) == (0.9, 1)
