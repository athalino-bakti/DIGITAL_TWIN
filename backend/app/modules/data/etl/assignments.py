"""Derivasi D-07 `assignments` dan `is_takeover` dari riwayat anggota kartu Trello (DIG-133).

Fungsi murni. Setiap `addMemberToCard` membuka masa penugasan anggota itu pada task kartu, dan
`removeMemberFromCard` menutupnya (`released_date`). Tanggal dalam WIB.

Takeover (AC DIG-29: "pergantian pelaksana menghasilkan assignment baru dengan is_takeover = true
dan released_date pada assignment lama"): assignment B adalah takeover bila ada assignment lain
pada task yang sama, milik anggota lain, yang dimulai lebih dulu dan sudah dilepas pada atau
sebelum tanggal mulai B. Ini sama dengan pola serah terima di `takeover_service` dan data sintetis
(assignment lama dilepas sehari sebelum, atau di hari yang sama dengan, assignment pengganti).
Anggota yang ditambahkan bersamaan tanpa ada yang dilepas bukan takeover.

Task yang punya riwayat anggota di Trello memakai assignment hasil derivasi ini; task tanpa
riwayat Trello tetap memakai satu assignment dari kolom PIC Project Plan (DIG-130, DIG-131).
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime

from app.modules.data.enums import IdentitySource
from app.modules.data.etl.identity import AliasIndex, resolve
from app.modules.data.etl.normalize import Candidates, Problem, to_wib_date
from app.modules.data.event_log import task_id_from_card
from app.modules.data.quality.engine import SourceRow

ADD, REMOVE = "addMemberToCard", "removeMemberFromCard"


@dataclass(frozen=True)
class MemberEvent:
    card_name: str | None
    action_type: str  # ADD atau REMOVE
    member_id: str | None
    member_name: str | None
    at: datetime


@dataclass
class Stint:
    member_id: str
    member_name: str | None
    started_at: datetime
    assigned: date
    released: date | None = None


def stints_per_task(events: Iterable[MemberEvent]) -> dict[str, list[Stint]]:
    """Masa penugasan per anggota per task, urut waktu mulai."""
    stints: dict[str, list[Stint]] = defaultdict(list)
    open_: dict[tuple[str, str], Stint] = {}
    for event in sorted(events, key=lambda e: e.at):
        task_id = task_id_from_card(event.card_name)
        if task_id is None or not event.member_id:
            continue
        key = (task_id, event.member_id)
        if event.action_type == ADD and key not in open_:
            stint = Stint(event.member_id, event.member_name, event.at, to_wib_date(event.at))
            open_[key] = stint
            stints[task_id].append(stint)
        elif event.action_type == REMOVE and key in open_:
            open_.pop(key).released = to_wib_date(event.at)
    return stints


def is_takeover(stint: Stint, others: list[Stint]) -> bool:
    return any(
        other.member_id != stint.member_id
        and other.started_at < stint.started_at
        and other.released is not None
        and other.released <= stint.assigned
        for other in others
    )


def derive_assignments(
    events: Iterable[MemberEvent], index: AliasIndex, roles: Mapping[str, str]
) -> tuple[dict[str, list[SourceRow]], list[Problem]]:
    """({task_id: kandidat assignments}, masalah). `roles` = {task_id: required_role_id}.

    Id member Trello diterjemahkan ke `resource_id` lewat `resource_alias` (DIG-131); yang belum
    dipetakan dilaporkan dan `resource_id`-nya dikosongkan agar ditolak validator.
    """
    rows: dict[str, list[SourceRow]] = {}
    problems: list[Problem] = []
    for task_id, stints in stints_per_task(events).items():
        rows[task_id] = []
        for stint in stints:
            resource_id = resolve(index, IdentitySource.TRELLO, stint.member_id)
            if resource_id is None:
                label = stint.member_name or stint.member_id
                problems.append(
                    Problem("trello", None, task_id, "resource_id", stint.member_id,
                            f"Anggota Trello '{label}' belum dipetakan ke anggota tim "
                            "(resource_alias)")
                )  # fmt: skip
            rows[task_id].append(
                SourceRow(
                    None,
                    None,  # assignment_id dibuat saat upsert (DIG-134)
                    {
                        "assignment_id": "",
                        "task_id": task_id,
                        "resource_id": resource_id or "",
                        "role_in_task": roles.get(task_id, ""),
                        "assigned_date": stint.assigned.isoformat(),
                        "released_date": stint.released.isoformat() if stint.released else "",
                        "is_takeover": "true" if is_takeover(stint, stints) else "false",
                    },
                )
            )
    return rows, problems


def merge_assignments(
    candidates: Candidates, events: Iterable[MemberEvent], index: AliasIndex
) -> Candidates:
    """Ganti kandidat assignment Project Plan dengan riwayat Trello bila task punya riwayat."""
    roles = {
        row.values["task_id"]: row.values.get("required_role_id", "")
        for row in candidates.tables["tasks"]
        if row.values.get("task_id")
    }
    trello, problems = derive_assignments(events, index, roles)
    kept = [r for r in candidates.tables["assignments"] if r.values.get("task_id") not in trello]
    derived = [row for task_id in sorted(trello) if task_id in roles for row in trello[task_id]]
    # PIC Project Plan yang tidak terpetakan tidak relevan bila assignment diambil dari Trello.
    plan_problems = [
        p for p in candidates.problems
        if not (p.source == "project_plan" and p.column == "resource_id" and p.key in trello)
    ]  # fmt: skip
    return Candidates(
        tables={**candidates.tables, "assignments": kept + derived},
        problems=plan_problems + [p for p in problems if p.key in roles],
    )
