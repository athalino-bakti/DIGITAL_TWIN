"""DIG-149: aturan isi D-10 change_events. Tanpa basis data."""

from datetime import date

import pytest

from app.modules.data.change_event_service import check_change_event_rules

START = date(2026, 1, 5)


def event(**overrides) -> dict:
    values = {
        "project_id": "PRJ-001",
        "event_type": "change_request",
        "event_date": date(2026, 3, 2),
        "requested_by": "Kaur",
        "decision": "accept_now",
        "resolution_mode": "swap_task",
        "affected_task_id": "TSK-0001",
        "extension_days": 0.0,
    }
    return values | overrides


def fields(values, project_start=START, task_project="PRJ-001") -> list[str]:
    return [e.field for e in check_change_event_rules(values, project_start, task_project)]


def test_valid_event():
    assert fields(event()) == []


def test_only_required_columns_is_valid():
    values = event(
        requested_by=None,
        decision=None,
        resolution_mode=None,
        affected_task_id=None,
        extension_days=None,
    )
    assert fields(values, task_project=None) == []


@pytest.mark.parametrize("event_type", ["change_request", "blocker", "overrun", "hotfix"])
@pytest.mark.parametrize("decision", ["accept_now", "defer_next", "reject"])
@pytest.mark.parametrize("mode", ["swap_task", "scope_addition", "reshuffle"])
def test_every_combination_from_dosbim_dataset_is_valid(event_type, decision, mode):
    """Dataset dosbim memuat semua kombinasi, termasuk reject dengan mode resolusi."""
    values = event(event_type=event_type, decision=decision, resolution_mode=mode)
    assert fields(values) == []


def test_unknown_project_reports_only_the_project():
    assert fields(event(), project_start=None, task_project="PRJ-002") == ["project_id"]


def test_event_before_project_start():
    errors = check_change_event_rules(event(event_date=date(2026, 1, 4)), START, "PRJ-001")
    assert [(e.field, e.error_type) for e in errors] == [("event_date", "before_project_start")]
    assert "2026-01-05" in errors[0].message


def test_event_on_project_start_day_is_valid():
    assert fields(event(event_date=START)) == []


def test_unknown_task():
    assert fields(event(), task_project=None) == ["affected_task_id"]


def test_task_from_other_project():
    errors = check_change_event_rules(event(), START, "PRJ-002")
    assert [e.error_type for e in errors] == ["task_other_project"]
    assert "PRJ-002" in errors[0].message


def test_extend_duration_needs_positive_days():
    for days in (None, 0.0):
        values = event(resolution_mode="extend_duration", extension_days=days)
        assert fields(values) == ["extension_days"]
    assert fields(event(resolution_mode="extend_duration", extension_days=1.9)) == []


@pytest.mark.parametrize("mode", ["swap_task", "scope_addition", "reshuffle", None])
def test_days_only_for_extend_duration(mode):
    assert fields(event(resolution_mode=mode, extension_days=2.0)) == ["extension_days"]
    assert fields(event(resolution_mode=mode, extension_days=0.0)) == []
    assert fields(event(resolution_mode=mode, extension_days=None)) == []


def test_mode_needs_decision():
    errors = check_change_event_rules(event(decision=None), START, "PRJ-001")
    assert [(e.field, e.error_type) for e in errors] == [("decision", "mode_needs_decision")]


def test_decision_without_mode_is_valid():
    assert fields(event(resolution_mode=None)) == []
