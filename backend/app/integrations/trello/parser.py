"""Parser ekspor JSON papan Trello ke baris staging_trello_action (DIG-118).

Input adalah `dict` hasil `json.load` berkas ekspor papan (Menu > Print, export, and share >
Export as JSON) atau hasil `TrelloClient.fetch_board_export()`; keduanya berbentuk sama.
Parser murni: tidak menyentuh basis data dan tidak mengubah input. Penyimpanan ke staging ada
di `app.modules.data.trello_staging`.

Aturan:
- Ekspor manual memuat semua jenis action, sedangkan konektor API sudah memfilter. Parser
  memakai filter yang sama (`ACTION_FILTER`) agar kedua jalur menghasilkan baris yang sama.
- Urutan input tidak dipakai (ekspor terbaru lebih dulu, data kotor bisa berantakan); keluaran
  diurutkan menurut waktu action lalu id.
- Satu action rusak tidak menghentikan parsing; action itu dilewati dan alasannya dicatat.
- Pelaku diambil dari `memberCreator` bila ada, atau dari `members` papan lewat
  `idMemberCreator`. Pemetaan akun Trello ke `resource_id` bukan tugas parser (DIG-24).
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.integrations.trello.client import ACTION_FILTER, PAGE_LIMIT
from app.modules.data.staging_models import TRELLO_ID_PATTERN

ACTION_TYPES = frozenset(ACTION_FILTER.split(","))
_TRELLO_ID = re.compile(TRELLO_ID_PATTERN)
# Action yang hanya membawa `data.list`: list itu posisi asal kartu, bukan tujuannya.
LIST_IS_BEFORE = frozenset({"deleteCard", "moveCardFromBoard"})


@dataclass
class TrelloParseReport:
    total: int = 0
    per_type: Counter[str] = field(default_factory=Counter)
    # (id action atau None bila id tidak terbaca, alasan)
    skipped: list[tuple[str | None, str]] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    # Akun Trello di papan dan pelaku action, dengan jumlah action sebagai pelaku.
    members: list[dict[str, Any]] = field(default_factory=list)
    unknown_creators: int = 0
    # Ekspor manual dilaporkan hanya memuat 1000 action terbaru (docs/TRELLO_API.md).
    possibly_truncated: bool = False

    def skipped_by_reason(self) -> Counter[str]:
        return Counter(reason for _, reason in self.skipped)


@dataclass(frozen=True)
class TrelloParseResult:
    board_id: str
    # Satu dict per baris staging_trello_action (kunci = nama kolom, tanpa imported_at).
    actions: list[dict[str, Any]]
    # (list_id, list_name) untuk didaftarkan ke trello_list_mapping.
    lists: list[tuple[str, str]]
    report: TrelloParseReport


class _Skip(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and _TRELLO_ID.fullmatch(value) is not None


def parse_board_export(board: Mapping[str, Any]) -> TrelloParseResult:
    """Ubah objek papan Trello menjadi baris staging dan laporan parsing.

    Melempar ValueError hanya bila objek papan sendiri tidak bisa dipakai (bukan objek, id
    papan tidak sah, atau `actions` bukan list).
    """
    if not isinstance(board, Mapping):
        raise ValueError("Ekspor Trello harus berupa objek papan")
    board_id = board.get("id")
    if not _is_id(board_id):
        raise ValueError("Objek papan Trello tidak punya id yang sah")
    actions = board.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Objek papan Trello tidak punya daftar actions")

    members = {
        m["id"]: m
        for m in board.get("members") or []
        if isinstance(m, Mapping) and _is_id(m.get("id"))
    }
    report = TrelloParseReport(total=len(actions), possibly_truncated=len(actions) == PAGE_LIMIT)
    rows: dict[str, dict[str, Any]] = {}
    creators: Counter[str] = Counter()
    extra_members: dict[str, Mapping[str, Any]] = {}

    for action in actions:
        action_id = action.get("id") if isinstance(action, Mapping) else None
        try:
            row = _action_row(action, board_id, members)
        except _Skip as skip:
            report.skipped.append((action_id if isinstance(action_id, str) else None, skip.reason))
            continue
        if row["action_id"] in rows:
            report.duplicates.append(row["action_id"])
            if rows[row["action_id"]]["raw"] != row["raw"]:
                report.skipped.append((row["action_id"], "duplikat_isi_berbeda"))
            continue
        rows[row["action_id"]] = row
        report.per_type[row["action_type"]] += 1
        creator_id = row["member_creator_id"]
        if creator_id:
            creators[creator_id] += 1
            if creator_id not in members:
                if isinstance(action.get("memberCreator"), Mapping):
                    extra_members[creator_id] = action["memberCreator"]
                else:
                    report.unknown_creators += 1

    report.members = [
        {
            "id": member_id,
            "username": member.get("username"),
            "fullName": member.get("fullName"),
            "actions": creators[member_id],
        }
        for member_id, member in {**members, **extra_members}.items()
    ]
    return TrelloParseResult(
        board_id=board_id,
        actions=sorted(rows.values(), key=lambda r: (r["action_date"], r["action_id"])),
        lists=_lists(board, report),
        report=report,
    )


def _action_row(
    action: Any, board_id: str, members: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    if not isinstance(action, Mapping):
        raise _Skip("rusak:bukan_objek")
    action_id = action.get("id")
    if not _is_id(action_id):
        raise _Skip("id_tidak_sah:id")
    kind = action.get("type")
    if not isinstance(kind, str):
        raise _Skip("rusak:type")
    if kind not in ACTION_TYPES:
        raise _Skip(f"jenis_di_luar_filter:{kind}")
    action_date = _utc(action.get("date"))
    data = action.get("data")
    if not isinstance(data, Mapping):
        raise _Skip("rusak:data")

    card_id, card_name = _ref(data, "card")
    before = _ref(data, "listBefore")
    after = _ref(data, "listAfter")
    if before == after == (None, None) and "list" in data:
        single = _ref(data, "list")
        if kind in LIST_IS_BEFORE:
            before = single
        else:
            after = single
    old = data.get("old")
    if kind == "updateList" and isinstance(old, Mapping) and isinstance(old.get("name"), str):
        before = (after[0], old["name"])  # ganti nama list: nama lama -> nama baru

    creator = action.get("memberCreator")
    creator_id = action.get("idMemberCreator")
    if creator_id is None and isinstance(creator, Mapping):
        creator_id = creator.get("id")
    if creator_id is not None and not _is_id(creator_id):
        raise _Skip("id_tidak_sah:idMemberCreator")
    if not isinstance(creator, Mapping):
        creator = members.get(creator_id, {})

    return {
        "action_id": action_id,
        "action_type": kind,
        "action_date": action_date,
        "board_id": board_id,
        "card_id": card_id,
        "card_name": card_name,
        "list_before_id": before[0],
        "list_before_name": before[1],
        "list_after_id": after[0],
        "list_after_name": after[1],
        "member_creator_id": creator_id,
        "member_creator_username": creator.get("username"),
        "member_creator_full_name": creator.get("fullName"),
        "raw": action,
    }


def _ref(data: Mapping[str, Any], key: str) -> tuple[str | None, str | None]:
    """(id, name) dari objek rujukan seperti data.card atau data.listAfter."""
    value = data.get(key)
    if value is None:
        return None, None
    if not isinstance(value, Mapping):
        raise _Skip(f"rusak:{key}")
    ref_id, name = value.get("id"), value.get("name")
    if ref_id is not None and not _is_id(ref_id):
        raise _Skip(f"id_tidak_sah:{key}")
    if name is not None and not isinstance(name, str):
        raise _Skip(f"rusak:{key}.name")
    return ref_id, name


def _utc(value: Any) -> datetime:
    """Waktu action Trello (`2026-10-01T08:00:00.000Z`) sebagai datetime UTC."""
    if not isinstance(value, str):
        raise _Skip("tanggal_tidak_sah")
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        raise _Skip("tanggal_tidak_sah") from None
    if moment.tzinfo is None:
        raise _Skip("tanggal_tidak_sah")
    return moment.astimezone(UTC)


def _lists(board: Mapping[str, Any], report: TrelloParseReport) -> list[tuple[str, str]]:
    """Semua list papan, termasuk yang diarsipkan, untuk trello_list_mapping."""
    lists = []
    for item in board.get("lists") or []:
        list_id = item.get("id") if isinstance(item, Mapping) else None
        if _is_id(list_id) and isinstance(item.get("name"), str):
            lists.append((list_id, item["name"]))
        else:
            report.skipped.append((list_id if isinstance(list_id, str) else None, "list_tidak_sah"))
    return lists
