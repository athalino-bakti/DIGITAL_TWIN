"""DIG-99: aturan proyek yang bisa diuji tanpa database."""

import json
from datetime import date

import pytest
from pydantic import ValidationError

from app.modules.data.schemas import ProjectCreate, ProjectUpdate
from app.modules.data.service import check_project_rules, is_active

VALID = {
    "project_name": "Sistem Presensi Pegawai",
    "process_owner": "Urusan Kepegawaian",
    "priority_rank": 1,
    "start_date": "2026-08-24",
    "target_launch_date": "2026-12-09",
    "status": "development",
}


def rules(**overrides) -> list[tuple[str, str]]:
    values = ProjectCreate.model_validate_json(_json(VALID | overrides)).model_dump()
    return [(e.field, e.error_type) for e in check_project_rules(values)]


def _json(data: dict) -> str:
    return json.dumps(data)


def test_valid_project_has_no_rule_errors():
    assert rules() == []


@pytest.mark.parametrize("status", ["planning", "development", "testing", "on_hold"])
def test_actual_launch_date_must_be_empty_before_released(status):
    assert rules(status=status, actual_launch_date="2026-12-01") == [
        ("actual_launch_date", "actual_launch_not_released")
    ]


def test_released_requires_actual_launch_date():
    assert rules(status="released") == [("actual_launch_date", "actual_launch_required")]


def test_released_with_actual_launch_date_is_valid():
    assert rules(status="released", actual_launch_date="2026-12-15") == []


def test_actual_launch_date_cannot_precede_start():
    assert rules(status="released", actual_launch_date="2026-08-01") == [
        ("actual_launch_date", "date_order")
    ]


def test_target_cannot_precede_start():
    assert rules(target_launch_date="2026-08-23") == [("target_launch_date", "date_order")]


def test_target_on_start_date_is_allowed():
    assert rules(target_launch_date="2026-08-24") == []


@pytest.mark.parametrize("rank", [0, -1])
def test_priority_rank_starts_at_one(rank):
    with pytest.raises(ValidationError) as info:
        ProjectCreate.model_validate_json(_json(VALID | {"priority_rank": rank}))
    assert info.value.errors()[0]["loc"] == ("priority_rank",)


def test_priority_rank_fits_postgres_integer():
    ProjectCreate.model_validate_json(_json(VALID | {"priority_rank": 2_147_483_647}))
    with pytest.raises(ValidationError) as info:
        ProjectCreate.model_validate_json(_json(VALID | {"priority_rank": 2_147_483_648}))
    assert info.value.errors()[0]["loc"] == ("priority_rank",)


@pytest.mark.parametrize("field", ["project_name", "process_owner"])
def test_names_cannot_contain_nul(field):
    with pytest.raises(ValidationError) as info:
        ProjectCreate.model_validate_json(_json(VALID | {field: "SIP\u0000"}))
    assert info.value.errors()[0]["loc"] == (field,)


@pytest.mark.parametrize("rank", ["1", 1.5, True])
def test_priority_rank_must_be_an_integer(rank):
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate_json(_json(VALID | {"priority_rank": rank}))


@pytest.mark.parametrize(
    "value",
    # 01/12/2026 dibaca PostgreSQL sebagai 12 Januari, jadi harus ditolak di API.
    ["01/12/2026", "14 Oct 2026", "2026/09/10", "2026-9-1", "2026-12-01T00:00:00", 1767225600],
)
def test_dates_must_be_iso(value):
    with pytest.raises(ValidationError) as info:
        ProjectCreate.model_validate_json(_json(VALID | {"start_date": value}))
    assert info.value.errors()[0]["loc"] == ("start_date",)


def test_iso_date_is_parsed():
    project = ProjectCreate.model_validate_json(_json(VALID))
    assert project.start_date == date(2026, 8, 24)


@pytest.mark.parametrize("value", ["PRJ-1", "PRJ-0001", "prj-001", "PRJ-ABC"])
def test_project_id_format(value):
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate_json(_json(VALID | {"project_id": value}))


@pytest.mark.parametrize("field", ["project_name", "process_owner"])
def test_names_cannot_be_blank(field):
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate_json(_json(VALID | {field: "   "}))


def test_names_are_trimmed():
    project = ProjectCreate.model_validate_json(_json(VALID | {"project_name": "  SIP  "}))
    assert project.project_name == "SIP"


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate_json(_json(VALID | {"status": "selesai"}))


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate_json(_json(VALID | {"budget": 10}))


def test_update_cannot_change_project_id():
    with pytest.raises(ValidationError):
        ProjectUpdate.model_validate_json(_json({"project_id": "PRJ-009"}))


@pytest.mark.parametrize(
    ("status", "active"),
    [
        ("planning", True),
        ("development", True),
        ("testing", True),
        ("on_hold", False),
        ("released", False),
    ],
)
def test_active_statuses(status, active):
    assert is_active(status) is active
