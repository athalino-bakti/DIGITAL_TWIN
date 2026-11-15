"""DIG-165: pemetaan action Trello dan kejadian D-10 menjadi event, tanpa basis data."""

from datetime import UTC, date, datetime

import pytest

from app.modules.data.enums import ChangeEventType
from app.modules.data.event_log import (
    CHANGE_LABEL,
    Skip,
    change_event_time,
    task_id_from_card,
    trello_event,
)

BOARD, TODO, DOING = "b" * 24, "1" * 24, "2" * 24
WHEN = datetime(2026, 9, 1, 2, 0, tzinfo=UTC)


def action(action_type: str, **overrides) -> dict:
    return {
        "action_id": "a" * 24,
        "action_type": action_type,
        "action_date": WHEN,
        "board_id": BOARD,
        "card_id": "c" * 24,
        "card_name": "TSK-0001 | Rancang API",
        "list_before_id": None,
        "list_before_name": None,
        "list_after_id": None,
        "list_after_name": None,
        "member_creator_id": "m" * 24,
        "member_creator_username": "kaur",
        "raw": {"data": {}},
    } | overrides


@pytest.mark.parametrize(
    "name,expected",
    [
        ("TSK-0001 | Rancang API", "TSK-0001"),
        ("  TSK-12345 | panjang", "TSK-12345"),
        ("TSK-001 | tiga digit", None),
        ("WLI-0001 | tiket", None),
        ("Rancang API", None),
        (None, None),
        ("TSK-0001x | tempel", None),
    ],
)
def test_task_code_comes_from_card_name(name, expected):
    assert task_id_from_card(name) == expected


@pytest.mark.parametrize("kind", ["createCard", "copyCard", "convertToCardFromCheckItem"])
def test_card_creation_is_task_created(kind):
    event = trello_event(action(kind), "TSK-0001", {})
    assert (event["activity_kind"], event["activity"]) == ("created", "Task dibuat")
    assert (event["case_id"], event["source"], event["source_ref"]) == (
        "TSK-0001",
        "trello",
        "a" * 24,
    )
    assert (event["actor_source_id"], event["actor_name"], event["resource_id"]) == (
        "m" * 24,
        "kaur",
        None,
    )
    assert event["event_time"] == WHEN


def test_move_uses_list_name_until_list_is_mapped():
    move = action(
        "updateCard",
        list_before_id=TODO,
        list_before_name="To Do",
        list_after_id=DOING,
        list_after_name="Sedang Dikerjakan",
    )
    assert trello_event(move, "TSK-0001", {})["activity"] == "Sedang Dikerjakan"
    mapped = trello_event(move, "TSK-0001", {(BOARD, DOING): "in_progress"})
    assert (mapped["activity_kind"], mapped["activity"]) == ("status", "in_progress")


def test_archiving_card_is_its_own_activity():
    archived = action("updateCard", raw={"data": {"old": {"closed": False}}})
    assert trello_event(archived, "TSK-0001", {})["activity_kind"] == "archived"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"raw": {"data": {"old": {"desc": "lama"}}}}, "updateCard_tanpa_pindah_list"),
        ({"list_before_id": TODO, "list_after_id": TODO}, "updateCard_tanpa_pindah_list"),
    ],
)
def test_other_card_updates_are_skipped(overrides, reason):
    assert trello_event(action("updateCard", **overrides), "TSK-0001", {}) == Skip(reason)


def test_unrelated_action_type_is_skipped_with_reason():
    assert trello_event(action("createList"), "TSK-0001", {}) == Skip("jenis_createList")


def test_deleted_card():
    assert trello_event(action("deleteCard"), "TSK-0001", {})["activity"] == "Kartu dihapus"


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Data sintetis J&C: anggota di data.member.
        (
            {"data": {"idMember": "x" * 24, "member": {"id": "x" * 24, "name": "Sari"}}},
            ("x" * 24, "Sari"),
        ),
        # Ekspor Trello asli: anggota di action.member.
        (
            {"data": {"idMember": "y" * 24}, "member": {"id": "y" * 24, "username": "sarip"}},
            ("y" * 24, "sarip"),
        ),
    ],
)
def test_assignment_actor_is_the_member_added(raw, expected):
    added = trello_event(action("addMemberToCard", raw=raw), "TSK-0001", {})
    assert (added["activity_kind"], added["activity"]) == ("assignment", "Anggota ditugaskan")
    assert (added["actor_source_id"], added["actor_name"]) == expected
    removed = trello_event(action("removeMemberFromCard", raw=raw), "TSK-0001", {})
    assert removed["activity"] == "Anggota dilepas"


def test_change_event_is_end_of_day_wib():
    moment = change_event_time(date(2026, 9, 1))
    assert moment.isoformat() == "2026-09-01T23:59:59+07:00"
    assert moment.astimezone(UTC).isoformat() == "2026-09-01T16:59:59+00:00"


def test_every_change_event_type_has_an_indonesian_label():
    assert set(CHANGE_LABEL) == set(ChangeEventType)
    assert all(label.endswith(("dicatat", "diubah")) for label in CHANGE_LABEL.values())
