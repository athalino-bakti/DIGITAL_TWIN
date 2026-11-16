"""DIG-144: satu tes positif dan satu tes negatif per rule_id final sources, tanpa basis data.

Dataset kecil `CLEAN` lolos semua aturan. Setiap tes positif mengubah satu hal yang melanggar
aturan itu, lalu memastikan rule_id-nya muncul.
"""

import copy
from collections.abc import Callable

import pytest

from app.modules.data.quality import rules
from app.modules.data.quality.engine import RULES, SourceRow
from app.modules.data.quality.rules import PRIMARY_KEY, TABLES, validate_final_sources

CLEAN: dict[str, list[dict[str, str]]] = {
    "projects": [
        {
            "project_id": "PRJ-001",
            "project_name": "Presensi",
            "process_owner": "Biro SDM",
            "priority_rank": "1",
            "start_date": "2026-09-01",
            "target_launch_date": "2026-12-01",
            "actual_launch_date": "",
            "status": "development",
            "dor_fulfilled": "false",
        }
    ],
    "resources": [
        {
            "resource_id": "RES-001",
            "resource_name": "Sari",
            "primary_role_id": "ROLE-BE",
            "secondary_role_ids": "ROLE-DM;ROLE-FE",
            "cross_role_capable": "true",
            "join_date": "2024-01-02",
            "seniority": "mid",
        }
    ],
    "roles": [
        {
            "role_id": "ROLE-BE",
            "role_name": "Back-End Developer",
            "capacity_reference": "3.0",
            "description": "",
        },
        {
            "role_id": "ROLE-QA",
            "role_name": "Quality Assurance",
            "capacity_reference": "3",
            "description": "Pengujian",
        },
    ],
    "complexity_levels": [
        {
            "complexity_id": "CX-M",
            "complexity_name": "Medium",
            "min_days": "3",
            "max_days": "5",
            "load_weight": "1.0",
        }
    ],
    "tasks": [
        {
            "task_id": "TSK-0001",
            "project_id": "PRJ-001",
            "feature_name": "Rekap",
            "task_name": "API rekap",
            "required_role_id": "ROLE-BE",
            "complexity_id": "CX-M",
            "priority_rank": "1",
            "estimated_days": "4",
            "phase": "be_dev",
            "planned_start": "2026-09-01",
            "planned_finish": "2026-09-04",
            "actual_start": "2026-09-01",
            "actual_finish": "2026-09-04",
            "status": "done",
            "qa_reject_count": "0",
            "dod_fulfilled": "true",
        },
        {
            "task_id": "TSK-0002",
            "project_id": "PRJ-001",
            "feature_name": "Rekap",
            "task_name": "Uji rekap",
            "required_role_id": "ROLE-QA",
            "complexity_id": "CX-M",
            "priority_rank": "2",
            "estimated_days": "3.5",
            "phase": "testing",
            "planned_start": "2026-09-07",
            "planned_finish": "2026-09-10",
            "actual_start": "2026-09-07",
            "actual_finish": "",
            "status": "in_progress",
            "qa_reject_count": "1",
            "dod_fulfilled": "false",
        },
    ],
    "task_dependencies": [
        {
            "dependency_id": "DEP-001",
            "task_id": "TSK-0002",
            "depends_on_task_id": "TSK-0001",
            "dependency_type": "hard",
            "propagation_factor": "1.0",
        }
    ],
    "assignments": [
        {
            "assignment_id": "ASG-0001",
            "task_id": "TSK-0001",
            "resource_id": "RES-001",
            "role_in_task": "ROLE-BE",
            "assigned_date": "2026-09-01",
            "released_date": "2026-09-04",
            "is_takeover": "false",
        }
    ],
    "workload_items": [
        {
            "item_id": "WLI-0001",
            "resource_id": "RES-001",
            "item_type": "ticket",
            "related_project_id": "PRJ-001",
            "received_date": "2026-09-02",
            "started_date": "2026-09-02",
            "resolved_date": "2026-09-03",
            "severity": "high",
            "is_hotfix": "false",
        }
    ],
    "availability": [
        {
            "availability_id": "AVL-001",
            "resource_id": "RES-001",
            "date_start": "2026-10-01",
            "date_end": "2026-10-02",
            "absence_type": "planned_leave",
            "is_known_at_planning": "true",
        }
    ],
    "change_events": [
        {
            "event_id": "EVT-001",
            "project_id": "PRJ-001",
            "event_type": "change_request",
            "event_date": "2026-09-05",
            "requested_by": "Kaur",
            "decision": "accept_now",
            "resolution_mode": "extend_duration",
            "affected_task_id": "TSK-0002",
            "extension_days": "2",
        }
    ],
    "holidays": [{"holiday_date": "2026-08-17", "holiday_name": "Hari Kemerdekaan"}],
}

UNKNOWN = {
    "projects": "PRJ-999",
    "roles": "ROLE-XX",
    "complexity_levels": "CX-XX",
    "tasks": "TSK-9999",
    "resources": "RES-999",
}
NEW_KEY = {
    "projects": "PRJ-002",
    "resources": "RES-002",
    "roles": "ROLE-TW",
    "complexity_levels": "CX-H",
    "tasks": "TSK-0003",
    "assignments": "ASG-0002",
    "workload_items": "WLI-0002",
    "availability": "AVL-002",
    "change_events": "EVT-002",
}
Data = dict[str, list[dict[str, str]]]


def to_tables(data: Data) -> dict[str, list[SourceRow]]:
    return {
        table: [
            SourceRow(number, values.get(PRIMARY_KEY[table]) or None, values)
            for number, values in enumerate(rows, start=2)
        ]
        for table, rows in data.items()
    }


def found(data: Data) -> set[str]:
    return {f.rule_id for f in validate_final_sources(to_tables(data)).findings}


# --- mutasi per nomor aturan -----------------------------------------------------------------


def _blank_required(data, table):
    column = [c for c in rules.REQUIRED[table] if c != PRIMARY_KEY[table]][-1]
    data[table][0][column] = ""


def _bad_id(data, table):
    data[table][0][PRIMARY_KEY[table]] = "X-1"


def _bad_enum(data, table):
    data[table][0][next(iter(rules.ENUMS[table]))] = "salah"


def _unknown_reference(data, table):
    column, target = rules.FOREIGN_KEYS[table][0]
    data[table][0][column] = UNKNOWN[target]


def _same_key(data, table):
    data[table].append(dict(data[table][0]))


def _same_content(data, table):
    data[table].append({**data[table][0], PRIMARY_KEY[table]: NEW_KEY[table]})


def _bad_date(data, table):
    column = next(c for c, k in rules.KINDS[table].items() if k == "date")
    data[table][0][column] = "01/12/2026"


def _bad_type(data, table):
    column = next(c for c, k in rules.KINDS[table].items() if k in ("int", "float", "bool"))
    data[table][0][column] = "abc"


def _date_order(data, table):
    start, end = next((a, b) for t, a, b in rules.DATE_ORDER if t == table)
    data[table][0][start], data[table][0][end] = "2026-09-10", "2026-09-01"


VALUE_MUTATION = {
    "projects": ("priority_rank", "0"),
    "roles": ("capacity_reference", "0"),
    "complexity_levels": ("min_days", "-1"),
    "tasks": ("estimated_days", "0"),
    "task_dependencies": ("propagation_factor", "1.5"),
    "change_events": ("extension_days", "-1"),
}


def _bad_value(data, table):
    column, value = VALUE_MUTATION[table]
    data[table][0][column] = value


def _set(table: str, row: int, **values) -> Callable[[Data, str], None]:
    def mutate(data, _table):
        data[table][row].update(values)

    return mutate


def _append(table: str, **values) -> Callable[[Data, str], None]:
    def mutate(data, _table):
        data[table].append({**data[table][0], **values})

    return mutate


GENERIC = {
    1: _blank_required,
    2: _bad_id,
    3: _bad_enum,
    4: _unknown_reference,
    5: _same_key,
    6: _same_content,
    7: _bad_date,
    8: _bad_type,
    9: _date_order,
    10: _bad_value,
}
SPECIFIC: dict[str, Callable[[Data, str], None]] = {
    "DQ-DEP-011": _append("task_dependencies", dependency_id="DEP-002"),
    "DQ-TSK-011": _set("tasks", 0, actual_start=""),
    "DQ-TSK-012": _set("tasks", 0, planned_start="2026-08-17"),
    "DQ-TSK-013": _set("tasks", 0, estimated_days="10"),
    "DQ-DEP-012": _append(
        "task_dependencies",
        dependency_id="DEP-002",
        task_id="TSK-0001",
        depends_on_task_id="TSK-0002",
    ),
    "DQ-DEP-013": _append(
        "task_dependencies",
        dependency_id="DEP-002",
        task_id="TSK-0001",
        depends_on_task_id="TSK-0002",
    ),
    "DQ-CHG-011": _set("change_events", 0, requested_by=""),
}

ROW_RULES = sorted(r.rule_id for r in RULES.values() if r.table in TABLES)


def mutation(rule_id: str):
    if rule_id in SPECIFIC:
        return SPECIFIC[rule_id]
    return GENERIC[int(rule_id.rsplit("-", 1)[1])]


def test_clean_dataset_has_no_findings():
    assert found(CLEAN) == set()
    report = validate_final_sources(to_tables(CLEAN))
    assert report.completeness_score() == 1.0
    assert report.rejected_rows() == []


@pytest.mark.parametrize("rule_id", ROW_RULES)
def test_rule_detects_violation(rule_id):
    data = copy.deepcopy(CLEAN)
    mutation(rule_id)(data, RULES[rule_id].table)
    assert rule_id in found(data)


@pytest.mark.parametrize("rule_id", ROW_RULES)
def test_rule_passes_clean_rows(rule_id):
    assert rule_id not in found(CLEAN)


# --- perilaku khusus -------------------------------------------------------------------------


def test_duplicate_key_rejects_later_rows_and_says_whether_identical():
    data = copy.deepcopy(CLEAN)
    data["tasks"].append(dict(data["tasks"][0]))
    data["tasks"].append({**data["tasks"][0], "task_name": "lain"})
    report = validate_final_sources(to_tables(data))
    hits = [f for f in report.findings if f.rule_id == "DQ-TSK-005"]
    assert [(f.row_number, f.message) for f in hits] == [
        (4, "task_id TSK-0001 sudah muncul di baris 2 dengan isi identik"),
        (5, "task_id TSK-0001 sudah muncul di baris 2 dengan isi berbeda"),
    ]
    rejected = report.rejected_rows()
    assert [(r["table"], r["row_number"]) for r in rejected] == [("tasks", 4), ("tasks", 5)]


def test_optional_columns_may_be_empty_but_are_checked_when_filled():
    data = copy.deepcopy(CLEAN)
    row = data["workload_items"][0]
    row.update(related_project_id="", started_date="", resolved_date="", severity="")
    assert found(data) == set()
    row["severity"] = "urgent"
    assert found(data) == {"DQ-WLI-003"}


def test_completeness_counts_required_cells():
    data = copy.deepcopy(CLEAN)
    data["tasks"][0]["estimated_days"] = ""
    data["tasks"][1]["planned_start"] = " "
    report = validate_final_sources(to_tables(data))
    filled, total = report.completeness["tasks"]
    assert (filled, total) == (total - 2, 2 * len(rules.REQUIRED["tasks"]))
    assert report.completeness_score("projects") == 1.0
    assert report.completeness_score() < 1.0


def test_summary_counts_checked_and_violating_rows():
    data = copy.deepcopy(CLEAN)
    data["tasks"][0].update(phase="x", status="y")  # dua pelanggaran, satu baris
    report = validate_final_sources(to_tables(data))
    summary = next(s for s in report.summaries if s.rule_id == "DQ-TSK-003")
    assert (summary.checked, summary.violated, summary.level) == (2, 1, "tolak")


def test_dependency_on_itself_and_hard_factor():
    data = copy.deepcopy(CLEAN)
    data["task_dependencies"][0].update(depends_on_task_id="TSK-0002", propagation_factor="0.3")
    messages = {
        f.message
        for f in validate_final_sources(to_tables(data)).findings
        if f.rule_id == "DQ-DEP-010"
    }
    assert messages == {
        "Task bergantung pada dirinya sendiri",
        "propagation_factor harus 1.0 untuk dependency hard",
    }
