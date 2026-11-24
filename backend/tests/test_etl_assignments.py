"""DIG-133: derivasi assignments dan is_takeover dari riwayat anggota kartu Trello."""

from datetime import UTC, datetime

from app.modules.data.etl.assignments import (
    ADD,
    REMOVE,
    MemberEvent,
    derive_assignments,
    merge_assignments,
)
from app.modules.data.etl.normalize import Candidates
from app.modules.data.quality.engine import SourceRow

SARI, BUDI, DEWI = "a" * 24, "b" * 24, "c" * 24
INDEX = {("trello", SARI): "RES-001", ("trello", BUDI): "RES-002", ("trello", DEWI): "RES-003"}
ROLES = {"TSK-0001": "ROLE-BE", "TSK-0002": "ROLE-FE"}


def event(kind, member, day, hour=3, card="TSK-0001 | API cuti", name=None):
    return MemberEvent(card, kind, member, name, datetime(2026, 11, day, hour, tzinfo=UTC))


def values(rows):
    return [
        (r.values["resource_id"], r.values["assigned_date"], r.values["released_date"],
         r.values["is_takeover"])
        for r in rows
    ]  # fmt: skip


def test_handover_marks_the_new_assignment_as_takeover():
    rows, problems = derive_assignments(
        [event(ADD, SARI, 2), event(REMOVE, SARI, 9), event(ADD, BUDI, 10)], INDEX, ROLES
    )
    assert problems == []
    assert values(rows["TSK-0001"]) == [
        ("RES-001", "2026-11-02", "2026-11-09", "false"),
        ("RES-002", "2026-11-10", "", "true"),
    ]
    assert {r.values["role_in_task"] for r in rows["TSK-0001"]} == {"ROLE-BE"}


def test_same_day_handover_is_a_takeover():
    rows, _ = derive_assignments(
        [event(ADD, SARI, 2), event(REMOVE, SARI, 10, hour=2), event(ADD, BUDI, 10, hour=4)],
        INDEX,
        ROLES,
    )
    assert [r.values["is_takeover"] for r in rows["TSK-0001"]] == ["false", "true"]


def test_members_added_together_are_not_takeovers():
    rows, _ = derive_assignments(
        [event(ADD, SARI, 2), event(ADD, BUDI, 2, hour=4), event(REMOVE, SARI, 9)], INDEX, ROLES
    )
    assert [r.values["is_takeover"] for r in rows["TSK-0001"]] == ["false", "false"]


def test_rejoining_member_is_not_a_takeover_of_itself():
    rows, _ = derive_assignments(
        [event(ADD, SARI, 2), event(REMOVE, SARI, 4), event(ADD, SARI, 6)], INDEX, ROLES
    )
    assert values(rows["TSK-0001"]) == [
        ("RES-001", "2026-11-02", "2026-11-04", "false"),
        ("RES-001", "2026-11-06", "", "false"),
    ]


def test_dates_use_wib_and_duplicate_or_orphan_events_are_ignored():
    rows, _ = derive_assignments(
        [
            event(REMOVE, DEWI, 1),  # lepas tanpa pernah ditambah
            event(ADD, SARI, 2, hour=20),  # 03.00 WIB tanggal 3
            event(ADD, SARI, 4),  # sudah aktif: diabaikan
        ],
        INDEX,
        ROLES,
    )
    assert values(rows["TSK-0001"]) == [("RES-001", "2026-11-03", "", "false")]


def test_unmapped_member_is_reported_not_guessed():
    stranger = "d" * 24
    rows, problems = derive_assignments([event(ADD, stranger, 2, name="Tamu")], INDEX, ROLES)
    assert rows["TSK-0001"][0].values["resource_id"] == ""
    (problem,) = problems
    assert (problem.source, problem.key, problem.column, problem.value) == (
        "trello",
        "TSK-0001",
        "resource_id",
        stranger,
    )
    assert "Tamu" in problem.message


def test_cards_without_task_code_are_skipped():
    rows, _ = derive_assignments([event(ADD, SARI, 2, card="Rapat mingguan")], INDEX, ROLES)
    assert rows == {}


def candidates() -> Candidates:
    result = Candidates()
    result.tables["tasks"] = [
        SourceRow(2, "TSK-0001", {"task_id": "TSK-0001", "required_role_id": "ROLE-BE"}),
        SourceRow(3, "TSK-0002", {"task_id": "TSK-0002", "required_role_id": "ROLE-FE"}),
    ]
    result.tables["assignments"] = [
        SourceRow(2, None, {"task_id": "TSK-0001", "resource_id": "RES-009", "pic": "Lama"}),
        SourceRow(3, None, {"task_id": "TSK-0002", "resource_id": "RES-003", "pic": "Dewi"}),
    ]
    return result


def test_trello_history_replaces_plan_pic_only_for_tasks_with_history():
    merged = merge_assignments(
        candidates(),
        [
            event(ADD, SARI, 2),
            event(REMOVE, SARI, 9),
            event(ADD, BUDI, 10),
            event(ADD, SARI, 2, card="TSK-0099 | Task di luar batch"),
        ],
        INDEX,
    )
    by_task = [(r.values["task_id"], r.values["resource_id"]) for r in merged.tables["assignments"]]
    assert by_task == [("TSK-0002", "RES-003"), ("TSK-0001", "RES-001"), ("TSK-0001", "RES-002")]
    assert merged.tables["tasks"] == candidates().tables["tasks"]
