"""Pembentukan event log dari staging Trello dan D-10 change_events (DIG-165, story DIG-37).

Satu task menjadi satu case. Kode task diambil dari nama kartu Trello (`TSK-0001 | ...`); kartu
beban non-proyek (`WLI-...`) dan kartu tanpa kode bukan case. Pemetaan action ke aktivitas:

- createCard, copyCard, convertToCardFromCheckItem: "Task dibuat";
- updateCard yang memindahkan kartu antarlist: status hasil pemetaan list (trello_list_mapping,
  DIG-120), atau nama list tujuan bila list itu belum dipetakan;
- updateCard yang mengarsipkan kartu: "Kartu diarsipkan";
- deleteCard: "Kartu dihapus";
- addMemberToCard / removeMemberFromCard: "Anggota ditugaskan" / "Anggota dilepas". Pelakunya
  anggota yang ditambah atau dilepas, karena dialah yang bekerja di case itu;
- D-10 change_events yang punya affected_task_id: aktivitas = label event_type (CHANGE_LABEL,
  misalnya "Blocker dicatat"). D-10 hanya menyimpan tanggal, jadi waktunya diletakkan di akhir
  hari itu (23:59:59 WIB): kejadian dicatat paling lambat hari itu, sehingga tidak pernah
  terurut sebelum aksi Trello pada hari yang sama (misalnya CR sebelum "Task dibuat").

Action lain dilewati dan dihitung per alasan di laporan. Riwayat commit (staging_commit, DIG-27)
belum ada dan akan menjadi sumber ketiga.

`org:resource` (resource_id) diisi lewat `resolve_resource`. Selama alias identitas (DIG-24)
belum ada, fungsinya selalu None dan akun pelaku tetap tersimpan di actor_source_id dan
actor_name, sehingga bangun ulang setelah DIG-24 cukup mengisi resource_id.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session

from app.modules.data.enums import ChangeEventType
from app.modules.data.event_log_models import EventLogEntry
from app.modules.data.models import ChangeEvent, Resource, Task
from app.modules.data.staging_models import StagingTrelloAction, TrelloListMapping
from app.modules.data.xes import XesEvent

WIB = timezone(timedelta(hours=7))
_TASK_CODE = re.compile(r"^(TSK-[0-9]{4,})\b")
CREATED_TYPES = frozenset({"createCard", "copyCard", "convertToCardFromCheckItem"})
# Bentuk "<hal> <kata kerja>" seperti aktivitas Trello ("Task dibuat", "Anggota ditugaskan").
CHANGE_LABEL = {
    ChangeEventType.CHANGE_REQUEST: "Change request dicatat",
    ChangeEventType.PRIORITY_CHANGE: "Prioritas diubah",
    ChangeEventType.BLOCKER: "Blocker dicatat",
    ChangeEventType.OVERRUN: "Overrun dicatat",
    ChangeEventType.HOTFIX: "Hotfix dicatat",
}


@dataclass(frozen=True)
class Skip:
    reason: str


def task_id_from_card(card_name: str | None) -> str | None:
    match = _TASK_CODE.match(card_name.strip()) if card_name else None
    return match.group(1) if match else None


def resolve_resource(actor_source_id: str | None, actor_name: str | None) -> str | None:
    """resource_id untuk akun pelaku. Kait DIG-131: dipakai setelah resource_alias (DIG-24) ada."""
    return None


def _assigned_member(raw: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """Anggota yang ditambah atau dilepas. Ekspor asli memakai action.member dan data.idMember;
    data sintetis menaruhnya di data.member."""
    data = raw.get("data") or {}
    member = raw.get("member") or data.get("member") or {}
    member_id = data.get("idMember") or member.get("id")
    name = member.get("username") or member.get("fullName") or member.get("name")
    return member_id, name


def trello_event(
    row: Mapping[str, Any], task_id: str, list_status: Mapping[tuple[str, str], str]
) -> dict[str, Any] | Skip:
    """Satu baris staging_trello_action menjadi satu event, atau Skip beserta alasannya."""
    kind_type = row["action_type"]
    raw = row["raw"] or {}
    actor = (row["member_creator_id"], row["member_creator_username"])

    if kind_type in CREATED_TYPES:
        kind, activity = "created", "Task dibuat"
    elif kind_type == "updateCard":
        before, after = row["list_before_id"], row["list_after_id"]
        old = (raw.get("data") or {}).get("old") or {}
        if before and after and before != after:
            kind = "status"
            activity = (
                list_status.get((row["board_id"], after))
                or row["list_after_name"]
                or "List tanpa nama"
            )
        elif old.get("closed") is False:
            kind, activity = "archived", "Kartu diarsipkan"
        else:
            return Skip("updateCard_tanpa_pindah_list")
    elif kind_type == "deleteCard":
        kind, activity = "deleted", "Kartu dihapus"
    elif kind_type in ("addMemberToCard", "removeMemberFromCard"):
        kind = "assignment"
        activity = "Anggota ditugaskan" if kind_type == "addMemberToCard" else "Anggota dilepas"
        actor = _assigned_member(raw)
    else:
        return Skip(f"jenis_{kind_type}")

    return {
        "case_id": task_id,
        "activity": activity[:100],
        "activity_kind": kind,
        "event_time": row["action_date"],
        "resource_id": resolve_resource(*actor),
        "actor_source_id": actor[0],
        "actor_name": actor[1],
        "source": "trello",
        "source_ref": row["action_id"],
    }


def day_start(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=WIB)


def change_event_time(event_date: date) -> datetime:
    """Akhir hari event_date (WIB). D-10 tidak menyimpan jam."""
    return datetime.combine(event_date, time(23, 59, 59), tzinfo=WIB)


@dataclass
class EventLogReport:
    events: int
    cases: int
    by_source: dict[str, int]
    by_kind: dict[str, int]
    cases_not_in_tasks: int
    events_without_resource: int
    skipped: dict[str, int]


def build_events(db: Session) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Semua event dari sumber yang ada, tanpa menulis ke basis data."""
    skipped: Counter[str] = Counter()
    columns = [c for c in StagingTrelloAction.__table__.columns]
    query = select(*columns).order_by(
        StagingTrelloAction.action_date, StagingTrelloAction.action_id
    )
    rows = [dict(r._mapping) for r in db.execute(query)]

    # Kartu yang pernah ganti kode task memakai kode dari nama terakhirnya.
    card_task: dict[str, str] = {}
    for row in rows:
        task = task_id_from_card(row["card_name"])
        if row["card_id"] and task:
            card_task[row["card_id"]] = task
    list_status = {
        (m.board_id, m.list_id): m.status
        for m in db.scalars(select(TrelloListMapping).where(TrelloListMapping.status.is_not(None)))
    }

    events: list[dict[str, Any]] = []
    for row in rows:
        if not row["card_id"]:
            skipped["bukan_action_kartu"] += 1
            continue
        task = card_task.get(row["card_id"])
        if task is None:
            name = (row["card_name"] or "").strip()
            skipped[
                "kartu_beban_non_proyek" if name.startswith("WLI-") else "kartu_tanpa_kode_task"
            ] += 1
            continue
        event = trello_event(row, task, list_status)
        if isinstance(event, Skip):
            skipped[event.reason] += 1
        else:
            events.append(event)

    for change in db.scalars(select(ChangeEvent)):
        if change.affected_task_id is None:
            skipped["change_event_tanpa_task"] += 1
            continue
        events.append(
            {
                "case_id": change.affected_task_id,
                "activity": CHANGE_LABEL.get(change.event_type, change.event_type),
                "activity_kind": "change_event",
                "event_time": change_event_time(change.event_date),
                "resource_id": None,
                "actor_source_id": None,
                "actor_name": change.requested_by,
                "source": "change_event",
                "source_ref": change.event_id,
            }
        )

    case_ids = {e["case_id"] for e in events}
    project_of = (
        dict(
            db.execute(
                select(Task.task_id, Task.project_id).where(Task.task_id.in_(case_ids))
            ).all()
        )
        if case_ids
        else {}
    )
    for event in events:
        event["project_id"] = project_of.get(event["case_id"])
    return events, skipped


def rebuild_event_log(db: Session) -> EventLogReport:
    """Hapus lalu isi ulang event_log dalam satu transaksi. Hasilnya sama bila diulang.

    Bangun ulang yang berjalan bersamaan menunggu giliran: tanpa kunci, DELETE milik yang
    kedua tidak melihat baris baru milik yang pertama, lalu INSERT-nya bentrok di UNIQUE
    (source, source_ref). EXCLUSIVE tetap mengizinkan SELECT, jadi GET /event-log tidak ikut
    tertahan. Kunci dilepas saat commit.
    """
    db.execute(text("LOCK TABLE event_log IN EXCLUSIVE MODE"))
    events, skipped = build_events(db)
    db.execute(delete(EventLogEntry))
    if events:
        db.execute(insert(EventLogEntry), events)
    db.commit()
    cases = {e["case_id"] for e in events}
    return EventLogReport(
        events=len(events),
        cases=len(cases),
        by_source=dict(Counter(e["source"] for e in events)),
        by_kind=dict(Counter(e["activity_kind"] for e in events)),
        cases_not_in_tasks=len({e["case_id"] for e in events if e["project_id"] is None}),
        events_without_resource=sum(1 for e in events if e["resource_id"] is None),
        skipped=dict(skipped),
    )


def list_event_log(
    db: Session,
    project_id: str | None = None,
    case_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[EventLogEntry]:
    """Event terurut per case lalu waktu. Rentang tanggal dihitung dalam WIB, inklusif."""
    query = select(EventLogEntry).order_by(
        EventLogEntry.case_id, EventLogEntry.event_time, EventLogEntry.event_id
    )
    if project_id is not None:
        query = query.where(EventLogEntry.project_id == project_id)
    if case_id is not None:
        query = query.where(EventLogEntry.case_id == case_id)
    if date_from is not None:
        query = query.where(EventLogEntry.event_time >= day_start(date_from))
    if date_to is not None:
        query = query.where(EventLogEntry.event_time < day_start(date_to + timedelta(1)))
    return list(db.scalars(query))


def xes_events(
    db: Session,
    project_id: str | None = None,
    case_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[XesEvent]:
    """Event untuk ekspor XES (DIG-173), urut per case; org:role = peran utama anggota."""
    # shortcut: baris dibaca sekaligus, hanya penulisan XML yang bertahap; pakai yield_per bila
    # event_log melewati ratusan ribu baris.
    entries = list_event_log(db, project_id, case_id, date_from, date_to)
    ids = {e.resource_id for e in entries if e.resource_id}
    roles = dict(
        db.execute(
            select(Resource.resource_id, Resource.primary_role_id).where(
                Resource.resource_id.in_(ids)
            )
        ).all()
    )
    return [
        XesEvent(
            case_id=e.case_id,
            activity=e.activity,
            event_time=e.event_time,
            project_id=e.project_id,
            activity_kind=e.activity_kind,
            resource_id=e.resource_id,
            actor_name=e.actor_name,
            role_id=roles.get(e.resource_id),
            source=e.source,
            source_ref=e.source_ref,
            event_id=e.event_id,
        )
        for e in entries
    ]
