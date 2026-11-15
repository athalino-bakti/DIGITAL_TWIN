"""Sumber mentah dari dunia simulasi yang sama (DIG-82).

- Project Plan per proyek (ekspor CSV Google Sheets, header dan status berbahasa Indonesia,
  tanggal dd/mm/yyyy, desimal koma).
- Ekspor JSON papan Trello (subset struktur ekspor Trello: lists, labels, members,
  cards, actions).
- git log per repositori proyek (format bawaan `git log --date=iso-strict`).

Identitas anggota sengaja berbeda di tiap tool. Pemetaannya ditulis ke
`ground_truth/identity_map.csv` sebagai kunci jawaban untuk tes entity resolution.
"""

import csv
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from synthetic import reference as ref
from synthetic.world import Assignment, Task, World

WIB = timezone(timedelta(hours=7))
ROLE_NAMES = {role_id: name for role_id, name, _ in ref.ROLES}
STATUS_LABEL = {
    "not_started": "Belum Mulai",
    "in_progress": "Dikerjakan",
    "blocked": "Terblokir",
    "on_hold": "Ditunda",
    "in_qa": "QA",
    "done": "Selesai",
    "dropped": "Dibatalkan",
}
PLAN_HEADER = [
    "No",
    "Kode",
    "Fitur",
    "Task",
    "Peran",
    "PIC",
    "Kompleksitas",
    "Prioritas",
    "Estimasi (hari)",
    "Mulai Rencana",
    "Selesai Rencana",
    "Mulai Aktual",
    "Selesai Aktual",
    "Status",
    "Bergantung Pada",
    "Catatan",
]
TRELLO_LISTS = ["Backlog", "To Do", "In Progress", "Blocked", "Hold", "QA", "Done"]
COMMIT_PREFIX = {"dm_dev": "feat(db)", "be_dev": "feat(api)", "fe_dev": "feat(ui)", "bugfix": "fix"}


def plan_date(value: date | None) -> str:
    return value.strftime("%d/%m/%Y") if value else ""


def plan_number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


class _Ids:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)

    def hex(self, length: int) -> str:
        return f"{self.rng.getrandbits(length * 4):0{length}x}"


def _assignments_by_task(world: World) -> dict[str, list[Assignment]]:
    result: dict[str, list[Assignment]] = {}
    for assignment in world.assignments:
        if assignment.assigned_date <= world.as_of:
            result.setdefault(assignment.task_id, []).append(assignment)
    return result


def _current_assignee(assignments: list[Assignment]) -> Assignment | None:
    active = [a for a in assignments if a.released_date is None]
    return (active or assignments or [None])[-1]


def _visible_tasks(world: World) -> list[Task]:
    return [t for t in world.tasks if t.min_start <= world.as_of]


# --------------------------------------------------------------------------- Project Plan


def project_plan_rows(world: World) -> dict[str, list[list[str]]]:
    """Baris Project Plan per project_id (tanpa header)."""
    by_task = _assignments_by_task(world)
    preds: dict[str, list[str]] = {}
    for dep in world.dependencies:
        preds.setdefault(dep.task_id, []).append(
            f"{dep.depends_on_task_id} ({dep.dependency_type})"
        )
    plans: dict[str, list[list[str]]] = {}
    for task in _visible_tasks(world):
        rows = plans.setdefault(task.project_id, [])
        assignments = by_task.get(task.task_id, [])
        current = _current_assignee(assignments)
        pic = world.resource(current.resource_id).aliases["project_plan_pic"] if current else ""
        notes = []
        if task.dropped:
            notes.append("Dibatalkan karena CR")
        for assignment in assignments:
            if assignment.is_takeover:
                notes.append(f"Dialihkan {plan_date(assignment.assigned_date)}")
        rows.append(
            [
                str(len(rows) + 1),
                task.task_id,
                task.feature_name,
                task.task_name,
                ROLE_NAMES[task.required_role_id],
                pic,
                ref.COMPLEXITY[task.complexity_id][0],
                str(task.priority_rank),
                plan_number(task.estimated_days),
                plan_date(task.planned_start),
                plan_date(task.planned_finish),
                plan_date(task.actual_start),
                plan_date(task.actual_finish),
                STATUS_LABEL[task.status],
                "; ".join(preds.get(task.task_id, [])),
                "; ".join(notes),
            ]
        )
    return plans


def write_project_plans(
    world: World, out_dir: Path, plans: dict[str, list[list[str]]]
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for project in world.projects:
        rows = plans.get(project.project_id)
        if not rows:
            continue
        name = f"project_plan_{project.project_id}.csv"
        with (out_dir / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(PLAN_HEADER)
            writer.writerows(rows)
        names.append(name)
    return names


# --------------------------------------------------------------------------- Trello


def _stamp(rng: random.Random, day: date) -> str:
    """Waktu kerja acak (WIB) dalam format UTC ekspor Trello."""
    local = datetime(
        day.year,
        day.month,
        day.day,
        rng.randint(8, 16),
        rng.randint(0, 59),
        rng.randint(0, 59),
        tzinfo=WIB,
    )
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def trello_board(world: World) -> dict[str, object]:
    ids = _Ids(world.seed + 1)
    rng = random.Random(world.seed + 2)
    board_id = ids.hex(24)
    lists = {name: ids.hex(24) for name in TRELLO_LISTS}
    members = {
        r.resource_id: {
            "id": ids.hex(24),
            "fullName": r.aliases["trello_fullname"],
            "username": r.aliases["trello_username"],
        }
        for r in world.resources
    }
    label_names = (
        [p.project_name for p in world.projects]
        + ["operasional", "tiket", "hotfix"]
        + [f"severity: {s}" for s in ("low", "medium", "high", "critical")]
    )
    labels = {name: ids.hex(24) for name in label_names}
    projects = {p.project_id: p for p in world.projects}
    events = {(e.affected_task_id, e.event_type): e for e in world.events if e.affected_task_id}
    by_task = _assignments_by_task(world)
    kaur = members["RES-001"]["id"]
    cards, actions = [], []

    def act(kind: str, day: date, card: dict, creator: str, **data: object) -> None:
        payload = {"card": {"id": card["id"], "name": card["name"]}, "board": {"id": board_id}}
        payload.update(data)
        actions.append(
            {
                "id": ids.hex(24),
                "type": kind,
                "date": _stamp(rng, day),
                "idMemberCreator": creator,
                "data": payload,
            }
        )

    def move(card: dict, day: date, before: str, after: str, creator: str) -> None:
        act(
            "updateCard",
            day,
            card,
            creator,
            listBefore={"id": lists[before], "name": before},
            listAfter={"id": lists[after], "name": after},
        )

    for task in _visible_tasks(world):
        project = projects[task.project_id]
        assignments = by_task.get(task.task_id, [])
        created = assignments[0].assigned_date if assignments else project.start_date
        if created > world.as_of:
            continue
        current_list = {
            "not_started": "To Do" if assignments else "Backlog",
            "in_progress": "In Progress",
            "blocked": "Blocked",
            "on_hold": "Hold",
            "in_qa": "QA",
            "done": "Done",
            "dropped": "Backlog",
        }[task.status]
        card = {
            "id": ids.hex(24),
            "name": f"{task.task_id} | {task.task_name}",
            "desc": f"Proyek: {project.project_name}\nFitur: {task.feature_name}",
            "idList": lists[current_list],
            "idLabels": [labels[project.project_name]],
            "idMembers": [
                members[a.resource_id]["id"] for a in assignments if a.released_date is None
            ],
            "closed": task.dropped,
            "dateLastActivity": None,
        }
        cards.append(card)
        act("createCard", created, card, kaur, list={"id": lists["Backlog"], "name": "Backlog"})
        for assignment in assignments:
            member = members[assignment.resource_id]
            act(
                "addMemberToCard",
                assignment.assigned_date,
                card,
                kaur,
                idMember=member["id"],
                member={"id": member["id"], "name": member["fullName"]},
            )
            if assignment.released_date:
                act(
                    "removeMemberFromCard",
                    assignment.released_date,
                    card,
                    kaur,
                    idMember=member["id"],
                    member={"id": member["id"], "name": member["fullName"]},
                )
        owner = members[assignments[-1].resource_id]["id"] if assignments else kaur
        position = "Backlog"
        if assignments:
            move(card, assignments[0].assigned_date, position, "To Do", kaur)
            position = "To Do"
        if task.actual_start:
            move(card, task.actual_start, position, "In Progress", owner)
            position = "In Progress"
        if task.status == "blocked":
            move(card, events[(task.task_id, "blocker")].event_date, position, "Blocked", owner)
        elif task.status == "on_hold" and project.hold_date:
            move(card, max(project.hold_date, created), position, "Hold", kaur)
        elif task.actual_finish:
            if task.status == "in_qa":
                move(card, task.actual_finish, position, "QA", owner)
            else:
                move(card, task.actual_finish, position, "Done", owner)
        elif task.dropped:
            act("updateCard", max(created, date(2026, 9, 21)), card, kaur, old={"closed": False})

    for item in world.workload_items:
        member = members[item.resource_id]
        tags = [
            "tiket" if item.item_type == "ticket" else "operasional",
            f"severity: {item.severity}",
        ]
        if item.is_hotfix:
            tags.append("hotfix")
        current_list = (
            "Done" if item.resolved_date else "In Progress" if item.started_date else "To Do"
        )
        card = {
            "id": ids.hex(24),
            "name": f"{item.item_id} | {item.title}",
            "desc": "",
            "idList": lists[current_list],
            "idLabels": [labels[t] for t in tags],
            "idMembers": [member["id"]],
            "closed": False,
            "dateLastActivity": None,
        }
        cards.append(card)
        act(
            "createCard",
            item.received_date,
            card,
            kaur,
            list={"id": lists["To Do"], "name": "To Do"},
        )
        if item.started_date:
            move(card, item.started_date, "To Do", "In Progress", member["id"])
        if item.resolved_date:
            move(card, item.resolved_date, "In Progress", "Done", member["id"])

    last_by_card: dict[str, str] = {}
    for action in actions:
        card_id = action["data"]["card"]["id"]
        last_by_card[card_id] = max(last_by_card.get(card_id, ""), action["date"])
    for card in cards:
        card["dateLastActivity"] = last_by_card.get(card["id"])
    actions.sort(key=lambda a: a["date"], reverse=True)
    return {
        "id": board_id,
        "name": "DEVTI - Pengembangan Aplikasi",
        "dateLastActivity": actions[0]["date"] if actions else None,
        "labels": [{"id": i, "name": n, "color": None} for n, i in labels.items()],
        "lists": [
            {"id": i, "name": n, "closed": False, "pos": (k + 1) * 1024}
            for k, (n, i) in enumerate(lists.items())
        ],
        "members": list(members.values()),
        "cards": cards,
        "actions": actions,
    }


# --------------------------------------------------------------------------- git log


def git_commits(world: World) -> dict[str, list[dict[str, str]]]:
    """Commit per project_id, terbaru di atas seperti keluaran `git log`."""
    ids = _Ids(world.seed + 3)
    rng = random.Random(world.seed + 4)
    by_task = _assignments_by_task(world)
    cal = world.calendar
    commits: dict[str, list[dict[str, str]]] = {}

    def commit(project_id: str, rid: str, day: date, message: str) -> None:
        resource = world.resource(rid)
        moment = datetime(
            day.year,
            day.month,
            day.day,
            rng.randint(8, 18),
            rng.randint(0, 59),
            rng.randint(0, 59),
            tzinfo=WIB,
        )
        commits.setdefault(project_id, []).append(
            {
                "hash": ids.hex(40),
                "author": resource.aliases["git_author"],
                "email": resource.aliases["git_email"],
                "date": moment.isoformat(),
                "message": message,
            }
        )

    for task in world.tasks:
        if task.phase not in COMMIT_PREFIX or task.actual_start is None:
            continue
        end = task.actual_finish or world.as_of
        day = task.actual_start
        assignments = by_task.get(task.task_id, [])
        while day <= end:
            owner = [
                a
                for a in assignments
                if a.assigned_date <= day and (a.released_date is None or a.released_date >= day)
            ]
            rid = (owner or assignments)[-1].resource_id if assignments else None
            if rid and cal.is_workday(day, rid, "actual"):
                for _ in range(rng.choice([0, 1, 1, 1, 2, 2, 3])):
                    subject = f"{COMMIT_PREFIX[task.phase]}: {task.task_name.lower()}"
                    if rng.random() < 0.85:
                        subject += f" [{task.task_id}]"
                    commit(task.project_id, rid, day, subject)
            day += timedelta(days=1)

    for item in world.workload_items:
        if item.is_hotfix and item.started_date:
            commit(
                item.related_project_id,
                item.resource_id,
                item.started_date,
                f"hotfix: perbaikan penyimpanan pengajuan cuti [{item.item_id}]",
            )

    for project_commits in commits.values():
        project_commits.sort(key=lambda c: c["date"], reverse=True)
    return commits


def format_git_log(entries: list[dict[str, str]]) -> str:
    blocks = []
    for entry in entries:
        blocks.append(
            f"commit {entry['hash']}\n"
            f"Author: {entry['author']} <{entry['email']}>\n"
            f"Date:   {entry['date']}\n\n"
            f"    {entry['message']}\n"
        )
    return "\n".join(blocks)


# --------------------------------------------------------------------------- penulis


def identity_rows(world: World) -> list[list[str]]:
    header = [
        "resource_id",
        "project_plan_pic",
        "trello_fullname",
        "trello_username",
        "git_author",
        "git_email",
    ]
    rows = [header]
    for resource in world.resources:
        aliases = resource.aliases
        rows.append([resource.resource_id] + [aliases[k] for k in header[1:]])
    return rows


def write_raw_sources(world: World, out_dir: Path) -> dict[str, object]:
    plans = project_plan_rows(world)
    plan_files = write_project_plans(world, out_dir / "project_plan", plans)
    board = trello_board(world)
    (out_dir / "trello").mkdir(parents=True, exist_ok=True)
    (out_dir / "trello" / "trello_board.json").write_text(
        json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    commits = git_commits(world)
    (out_dir / "git").mkdir(parents=True, exist_ok=True)
    for project_id, entries in sorted(commits.items()):
        (out_dir / "git" / f"{project_id}.log").write_text(
            format_git_log(entries), encoding="utf-8"
        )
    truth = out_dir.parent / "ground_truth"
    truth.mkdir(parents=True, exist_ok=True)
    with (truth / "identity_map.csv").open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle, lineterminator="\n").writerows(identity_rows(world))
    return {
        "project_plan": plan_files,
        "trello_cards": len(board["cards"]),
        "trello_actions": len(board["actions"]),
        "git_commits": {pid: len(entries) for pid, entries in sorted(commits.items())},
    }
