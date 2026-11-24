"""DIG-130: normalisasi staging ke baris kandidat tabel final, tanpa basis data."""

from datetime import UTC, datetime

import pytest

from app.modules.data.enums import TaskPhase, TaskStatus
from app.modules.data.etl.normalize import (
    PHASE_BY_ROLE,
    STATUS_LABELS,
    CardState,
    PlanRow,
    TrelloMove,
    build_candidates,
    card_states,
    label_index,
    normalize_date,
    normalize_decimal,
    normalize_integer,
    normalize_status,
    split_dependencies,
)

ROLES = label_index([("ROLE-BE", "Back End Developer"), ("ROLE-FE", "Front End Developer"),
                     ("ROLE-KAUR", "Kepala Urusan / Asisten Manajer")])  # fmt: skip
COMPLEXITIES = label_index([("CX-L", "Low"), ("CX-M", "Medium"), ("CX-H", "High")])
IMPORTED = datetime(2026, 11, 6, 3, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("value", "xlsx", "expected"),
    [
        ("05/10/2026", False, ("2026-10-05", None)),  # Project Plan CSV
        ("2026-10-05", True, ("2026-10-05", None)),  # sel tanggal XLSX
        ("2026-10-05", False, ("", "Tanggal '2026-10-05' tidak berformat dd/mm/yyyy")),
        (" 05/10/2026 ", False, ("2026-10-05", None)),
        ("", False, ("", None)),
        (None, True, ("", None)),
    ],
)
def test_dates_in_plan_or_iso_format(value, xlsx, expected):
    assert normalize_date(value, xlsx) == expected


@pytest.mark.parametrize(
    "value", ["5/10/2026", "2026/10/05", "5 Okt 2026", "31/02/2026", "11/9/26"]
)
def test_ambiguous_or_invalid_dates_are_reported(value):
    normalized, message = normalize_date(value, xlsx=True)
    assert normalized == "" and message and value.strip() in message


@pytest.mark.parametrize(
    ("label", "status"),
    [
        ("Belum Mulai", "not_started"),
        ("dikerjakan", "in_progress"),
        ("TERBLOKIR", "blocked"),
        ("Ditunda", "on_hold"),
        ("QA", "in_qa"),
        ("Selesai", "done"),
        ("Dibatalkan", "dropped"),
        ("in_progress", "in_progress"),  # enum D-05 langsung
    ],
)
def test_status_labels(label, status):
    assert normalize_status(label) == (status, None)


def test_every_task_status_is_reachable():
    assert set(STATUS_LABELS.values()) == set(TaskStatus)


@pytest.mark.parametrize("label", ["Sedang Dikerjakan", "Done!", "Review"])
def test_unknown_status_is_reported_not_guessed(label):
    assert normalize_status(label) == ("", f"Status '{label}' tidak dikenal")


@pytest.mark.parametrize(
    ("role", "phase"),
    [
        ("ROLE-SA", "planning"),
        ("ROLE-UIUX", "uiux"),
        ("ROLE-DM", "dm_dev"),
        ("ROLE-BE", "be_dev"),
        ("ROLE-FE", "fe_dev"),
        ("ROLE-QA", "testing"),
        ("ROLE-TW", "documentation"),
    ],
)
def test_phase_by_role(role, phase):
    assert PHASE_BY_ROLE[role].value == phase


@pytest.mark.parametrize(
    ("normalize", "value", "expected"),
    [
        (normalize_decimal, "2,5", ("2.5", None)),
        (normalize_decimal, "3", ("3", None)),
        (normalize_decimal, "2.5", ("2.5", None)),
        (normalize_decimal, "dua", ("", "Angka 'dua' tidak valid")),
        (normalize_integer, "03", ("3", None)),
        (normalize_integer, "1,5", ("", "Bilangan bulat '1,5' tidak valid")),
    ],
)
def test_numbers(normalize, value, expected):
    assert normalize(value) == expected


def test_dependencies_with_type_from_the_template():
    assert split_dependencies("TSK-0001 (hard); TSK-0002 (Soft),TSK-0001 (soft) ;") == [
        ("TSK-0001", "hard", None),
        ("TSK-0002", "soft", None),
    ]
    assert split_dependencies("TSK-0003") == [("TSK-0003", "hard", None)]  # tanpa tipe: hard
    assert split_dependencies(None) == []


def test_unknown_dependency_type_or_text_is_reported():
    assert split_dependencies("TSK-0001 (wajib); setelah rapat") == [
        ("TSK-0001", "", "Tipe dependensi 'wajib' tidak dikenal"),
        ("setelah rapat", "", "Dependensi 'setelah rapat' tidak terbaca"),
    ]


def move(card, list_id, hour):
    return TrelloMove(card, "b" * 24, list_id, datetime(2026, 11, 5, hour, tzinfo=UTC))


MAPPING = {("b" * 24, "L-QA"): ("in_qa", "testing"), ("b" * 24, "L-DONE"): ("done", None)}


def test_card_state_is_the_last_mapped_move():
    states = card_states(
        [
            move("TSK-0001 | Login", "L-DONE", 10),
            move("TSK-0001 | Login", "L-QA", 9),
            move("Kartu tanpa kode", "L-QA", 11),
            move("TSK-0002 | Logout", "L-UNMAPPED", 8),
        ],
        MAPPING,
    )
    assert states["TSK-0001"] == CardState(TaskStatus.DONE, None, move("", "", 10).at)
    assert states["TSK-0002"] == CardState(None, None, move("", "", 8).at)
    assert set(states) == {"TSK-0001", "TSK-0002"}


def plan_row(number=2, **overrides) -> PlanRow:
    values = {
        "task_code": "TSK-0001",
        "feature_name": "Cuti",
        "task_name": "API cuti",
        "role_label": "Back End Developer",
        "pic": "sari",
        "complexity_label": "Medium",
        "priority": "1",
        "estimated_days": "2,5",
        "planned_start": "02/11/2026",
        "planned_finish": "04/11/2026",
        "actual_start": "02/11/2026",
        "actual_finish": "",
        "status_label": "Dikerjakan",
        "depends_on": "TSK-0002 (hard); TSK-0003 (soft)",
        "notes": "",
    } | overrides
    return PlanRow(number, "PRJ-001", values, IMPORTED)


def test_plan_row_becomes_task_dependency_and_assignment_candidates():
    result = build_candidates([plan_row()], {}, ROLES, COMPLEXITIES)
    assert result.problems == []
    (task,) = result.tables["tasks"]
    assert (task.number, task.key) == (2, "TSK-0001")
    assert dict(task.values) == {
        "task_id": "TSK-0001",
        "project_id": "PRJ-001",
        "feature_name": "Cuti",
        "task_name": "API cuti",
        "required_role_id": "ROLE-BE",
        "complexity_id": "CX-M",
        "priority_rank": "1",
        "estimated_days": "2.5",
        "planned_start": "2026-11-02",
        "planned_finish": "2026-11-04",
        "actual_start": "2026-11-02",
        "actual_finish": "",
        "status": "in_progress",
        "phase": "be_dev",  # tanpa kartu Trello: dari peran
        "qa_reject_count": "0",
        "dod_fulfilled": "false",
    }
    assert [d.values["depends_on_task_id"] for d in result.tables["task_dependencies"]] == [
        "TSK-0002",
        "TSK-0003",
    ]
    types = [
        (d.values["dependency_type"], d.values["propagation_factor"])
        for d in result.tables["task_dependencies"]
    ]
    assert types == [("hard", "1.0"), ("soft", "0.3")]
    (assignment,) = result.tables["assignments"]
    assert (assignment.values["pic"], assignment.values["resource_id"]) == ("sari", "")
    assert assignment.values["assigned_date"] == "2026-11-02"


def test_newer_trello_status_wins_and_trello_phase_is_used():
    newer = CardState(TaskStatus.IN_QA, TaskPhase.TESTING, datetime(2026, 11, 6, 4, tzinfo=UTC))
    (task,) = build_candidates([plan_row()], {"TSK-0001": newer}, ROLES, COMPLEXITIES).tables[
        "tasks"
    ]
    assert (task.values["status"], task.values["phase"]) == ("in_qa", "testing")


def test_older_trello_status_loses_to_the_plan():
    older = CardState(TaskStatus.DONE, None, datetime(2026, 11, 5, tzinfo=UTC))
    (task,) = build_candidates([plan_row()], {"TSK-0001": older}, ROLES, COMPLEXITIES).tables[
        "tasks"
    ]
    assert (task.values["status"], task.values["phase"]) == ("in_progress", "be_dev")


def test_trello_fills_an_empty_plan_status():
    older = CardState(TaskStatus.DONE, None, datetime(2026, 11, 5, tzinfo=UTC))
    row = plan_row(status_label="")
    (task,) = build_candidates([row], {"TSK-0001": older}, ROLES, COMPLEXITIES).tables["tasks"]
    assert task.values["status"] == "done"


def test_unknown_labels_are_reported_and_left_empty():
    row = plan_row(
        role_label="Data Scientist",
        complexity_label="Sedang",
        status_label="Review",
        planned_start="2 Nov 2026",
        estimated_days="dua",
        priority="satu",
    )
    result = build_candidates([row], {}, ROLES, COMPLEXITIES)
    task = result.tables["tasks"][0].values
    for column in ("required_role_id", "complexity_id", "status", "planned_start",
                   "estimated_days", "priority_rank", "phase"):  # fmt: skip
        assert task[column] == ""
    reported = {(p.column, p.value) for p in result.problems}
    assert reported == {
        ("required_role_id", "Data Scientist"),
        ("complexity_id", "Sedang"),
        ("status", "Review"),
        ("planned_start", "2 Nov 2026"),
        ("estimated_days", "dua"),
        ("priority_rank", "satu"),
    }
    assert all((p.source, p.row, p.key) == ("project_plan", 2, "TSK-0001") for p in result.problems)


def test_role_without_phase_is_reported():
    result = build_candidates([plan_row(role_label="ROLE-KAUR")], {}, ROLES, COMPLEXITIES)
    assert result.tables["tasks"][0].values["phase"] == ""
    assert [(p.column, p.value) for p in result.problems] == [("phase", "ROLE-KAUR")]


def test_rows_without_pic_or_dependencies_add_nothing_else():
    result = build_candidates([plan_row(pic="", depends_on="")], {}, ROLES, COMPLEXITIES)
    assert result.tables["task_dependencies"] == [] and result.tables["assignments"] == []
