"""DIG-118: parser ekspor JSON Trello ke baris staging, tanpa basis data.

Fixture `fixtures/trello_board_kecil.json` dipangkas dari `trello_board.json` generator data
sintetis J&C (seed 42, DIG-16): tiga kartu (TSK-0052 sampai Done, WLI-0083 masih berjalan,
TSK-0096 diarsipkan), semua list papan, dan pelakunya. Dari versi kotor diambil akun kembar
`saripusp2` dan satu action yang tercatat dua kali. Kasus yang tidak dihasilkan generator
ditambahkan dengan tangan: `createList` dengan objek `memberCreator` (bentuk ekspor asli),
`updateList` ganti nama, list diarsipkan, `deleteCard`, `commentCard` (di luar filter),
`updateCard` tanpa perpindahan list oleh pelaku yang tidak dikenal, id rusak, tanggal tanpa
zona waktu, dan elemen yang bukan objek.
"""

import copy
import json
import random
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.integrations.trello import parser
from app.integrations.trello.client import ACTION_TYPES, PAGE_LIMIT, TrelloClient
from app.integrations.trello.parser import parse_board_export

FIXTURE = Path(__file__).parent / "fixtures" / "trello_board_kecil.json"
DUPLICATE = "5de414e3b40488cb2477b848"
REVIEW_LIST = "a" * 23 + "1"


@pytest.fixture
def board() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def by_type(result, kind: str) -> list[dict]:
    return [row for row in result.actions if row["action_type"] == kind]


def test_report_counts_kept_and_skipped_actions(board):
    report = parse_board_export(board).report

    assert report.total == 22
    assert sum(report.per_type.values()) == 16
    assert report.per_type["updateCard"] == 7
    assert report.skipped_by_reason() == {
        "tanggal_tidak_sah": 1,
        "id_tidak_sah:id": 1,
        "rusak:bukan_objek": 1,
        "jenis_di_luar_filter:commentCard": 1,
        "duplikat_isi_berbeda": 1,
    }
    assert report.possibly_truncated is False


def test_output_order_does_not_depend_on_input_order(board):
    expected = parse_board_export(board).actions
    shuffled = copy.deepcopy(board)
    random.Random(7).shuffle(shuffled["actions"])

    assert [r["action_id"] for r in parse_board_export(shuffled).actions] == [
        r["action_id"] for r in expected
    ]
    dates = [r["action_date"] for r in expected]
    assert dates == sorted(dates), "keluaran urut dari action terlama"


def test_dates_with_z_suffix_become_utc_datetimes(board):
    row = parse_board_export(board).actions[0]
    assert row["action_date"] == datetime(2026, 9, 7, 9, 32, 43, tzinfo=UTC)


def test_card_move_fills_list_before_and_after(board):
    move = next(
        r
        for r in by_type(parse_board_export(board), "updateCard")
        if r["list_after_name"] == "Done"
    )
    assert move["list_before_name"] == "In Progress"
    assert move["list_before_id"] and move["list_after_id"]
    assert move["card_name"].startswith("TSK-")


def test_create_card_puts_its_list_in_list_after(board):
    created = by_type(parse_board_export(board), "createCard")[0]
    assert (created["list_before_id"], created["list_after_name"]) == (None, "Backlog")


def test_update_card_without_list_change_is_kept(board):
    result = parse_board_export(board)
    archived = next(
        r for r in by_type(result, "updateCard") if r["raw"]["data"].get("old") == {"closed": False}
    )
    assert archived["card_name"].startswith("TSK-0096")
    assert archived["list_before_id"] is None and archived["list_after_id"] is None


def test_deleted_card_has_id_but_no_name(board):
    deleted = by_type(parse_board_export(board), "deleteCard")[0]
    assert deleted["card_id"] == "c" * 24
    assert deleted["card_name"] is None
    assert deleted["list_before_id"] is not None, "list asal kartu yang dihapus"
    assert deleted["list_after_id"] is None


def test_list_rename_records_old_and_new_name(board):
    renamed = by_type(parse_board_export(board), "updateList")[0]
    assert renamed["card_id"] is None
    assert (renamed["list_before_name"], renamed["list_after_name"]) == ("Review", "Code Review")
    assert renamed["list_before_id"] == renamed["list_after_id"] == REVIEW_LIST


def test_archived_lists_are_registered_for_mapping(board):
    lists = dict(parse_board_export(board).lists)
    assert len(lists) == 8
    assert lists[REVIEW_LIST] == "Code Review"


def test_creator_from_member_creator_object_or_board_members(board):
    result = parse_board_export(board)
    from_object = by_type(result, "createList")[0]
    from_lookup = by_type(result, "createCard")[0]

    assert "memberCreator" in from_object["raw"]
    assert "memberCreator" not in from_lookup["raw"]
    for row in (from_object, from_lookup):
        assert row["member_creator_username"] == "hendrawira"
        assert row["member_creator_full_name"]


def test_unknown_creator_keeps_id_without_name(board):
    result = parse_board_export(board)
    unknown = [r for r in result.actions if r["member_creator_id"] == "9" * 24]

    assert len(unknown) == 1 and unknown[0]["member_creator_username"] is None
    assert result.report.unknown_creators == 1


def test_member_report_lists_twin_account_without_actions(board):
    members = {m["username"]: m for m in parse_board_export(board).report.members}
    assert members["saripusp2"]["actions"] == 0
    assert members["saripusp"]["actions"] == 0
    assert members["hendrawira"]["actions"] == 11


def test_duplicate_action_keeps_first_copy(board):
    result = parse_board_export(board)
    kept = [r for r in result.actions if r["action_id"] == DUPLICATE]

    assert result.report.duplicates == [DUPLICATE, DUPLICATE]
    assert len(kept) == 1
    assert kept[0]["action_date"] == datetime(2026, 10, 20, 1, 15, 29, tzinfo=UTC)


def test_broken_actions_are_skipped_without_stopping(board):
    board["actions"].insert(0, {"id": "e" * 24, "type": "updateCard", "date": "x", "data": {}})
    board["actions"].insert(1, {"id": "e" * 23 + "f", "type": "updateCard", "data": []})
    board["actions"].append(
        {"id": "e" * 22 + "ff", "type": "updateCard", "date": "2026-10-01T00:00:00Z", "data": {}}
        | {"idMemberCreator": "BUKAN"}
    )
    result = parse_board_export(board)

    assert len(result.actions) == 16
    reasons = result.report.skipped_by_reason()
    assert reasons["tanggal_tidak_sah"] == 3
    assert reasons["id_tidak_sah:idMemberCreator"] == 1


def test_input_is_not_modified(board):
    before = copy.deepcopy(board)
    parse_board_export(board)
    assert board == before


def test_exactly_page_limit_actions_flags_possible_truncation(board):
    template = next(a for a in board["actions"] if isinstance(a, dict) and a["id"] == DUPLICATE)
    board["actions"] = [template | {"id": f"{i:024x}"} for i in range(PAGE_LIMIT)]
    assert parse_board_export(board).report.possibly_truncated is True


@pytest.mark.parametrize(
    "bad_board",
    [[], {"actions": []}, {"id": "abc", "actions": []}, {"id": "b" * 24, "actions": "x"}],
)
def test_unusable_board_object_raises(bad_board):
    with pytest.raises(ValueError):
        parse_board_export(bad_board)


def test_file_export_and_api_connector_give_same_rows(board):
    """Berkas ekspor dan konektor API (server Trello tiruan) menghasilkan baris staging sama."""

    def trello(request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/1")
        base = f"/boards/{board['id']}"
        if path == base:
            return httpx.Response(200, json={"id": board["id"], "name": board["name"]})
        if path == f"{base}/actions":
            # Seperti Trello: hanya jenis yang diminta, dan tidak ada elemen non-objek.
            wanted = set(request.url.params["filter"].split(","))
            actions = [a for a in board["actions"] if isinstance(a, dict) and a["type"] in wanted]
            return httpx.Response(200, json=actions)
        key = path.removeprefix(f"{base}/")
        return httpx.Response(200, json=board[key])

    client = TrelloClient("kunci", "token", transport=httpx.MockTransport(trello))
    from_api = parse_board_export(client.fetch_board_export(board["id"]))
    from_file = parse_board_export(board)

    assert from_api.actions == from_file.actions
    assert from_api.lists == from_file.lists
    assert "jenis_di_luar_filter:commentCard" not in from_api.report.skipped_by_reason()


def test_filter_matches_connector():
    assert parser.ACTION_TYPES is ACTION_TYPES
    assert "updateCard" in ACTION_TYPES and "commentCard" not in ACTION_TYPES
    assert len(ACTION_TYPES) == 11
