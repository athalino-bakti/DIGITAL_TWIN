"""Penyisipan data kotor untuk menguji validasi dan ETL (DIG-83).

Data bersih tidak diubah. Salinan kotor ditulis ke folder `dirty/` beserta
`manifest_cacat.csv` yang mencatat setiap cacat (sumber, berkas, lokasi, kolom, jenis,
nilai asli, nilai kotor) sebagai kunci jawaban tes.

Jenis cacat mengikuti anomali pada wireframe halaman Data dan acceptance criteria DIG-16:
format tanggal tidak konsisten, alias berbeda, baris ganda, siklus dependency, kolom wajib
kosong, referensi tidak dikenal, nilai enum salah, format ID salah, urutan tanggal terbalik.
"""

import copy
import csv
import json
import random
from datetime import date
from pathlib import Path

from synthetic import reference as ref
from synthetic.final_sources import final_source_rows, format_value
from synthetic.raw_sources import (
    PLAN_HEADER,
    format_git_log,
    git_commits,
    project_plan_rows,
    trello_board,
)
from synthetic.world import World

MANIFEST_HEADER = ["sumber", "berkas", "lokasi", "kolom", "jenis", "nilai_asli", "nilai_kotor"]


class _Defects:
    def __init__(self) -> None:
        self.rows: list[list[str]] = []

    def add(
        self,
        source: str,
        file: str,
        where: str,
        column: str,
        kind: str,
        before: object,
        after: object,
    ) -> None:
        self.rows.append([source, file, where, column, kind, str(before), str(after)])


def _id_date(value: str) -> date:
    return date.fromisoformat(value)


# --------------------------------------------------------------------------- final sources


def dirty_final_sources(world: World, rng: random.Random, log: _Defects) -> dict[str, list]:
    tables = {
        table: [{k: format_value(v) for k, v in row.items()} for row in rows]
        for table, rows in final_source_rows(world).items()
    }

    def pick(table: str, condition=lambda r: True) -> tuple[int, dict]:
        candidates = [(i, r) for i, r in enumerate(tables[table]) if condition(r)]
        return rng.choice(candidates)

    def set_value(table: str, index: int, column: str, value: str, kind: str) -> None:
        row = tables[table][index]
        key = row[ref.HEADERS[table][0]]
        log.add(
            "final_sources",
            f"{table}.csv",
            f"{ref.HEADERS[table][0]}={key}",
            column,
            kind,
            row[column],
            value,
        )
        row[column] = value

    # Kolom wajib kosong.
    i, _ = pick("tasks")
    set_value("tasks", i, "estimated_days", "", "wajib_kosong")
    i, _ = pick("resources")
    set_value("resources", i, "join_date", "", "wajib_kosong")

    # Format tanggal tidak konsisten.
    i, row = pick("tasks", lambda r: r["planned_start"] != "")
    set_value(
        "tasks",
        i,
        "planned_start",
        _id_date(row["planned_start"]).strftime("%d/%m/%Y"),
        "format_tanggal",
    )
    i, row = pick("assignments")
    set_value(
        "assignments",
        i,
        "assigned_date",
        _id_date(row["assigned_date"]).strftime("%d %b %Y"),
        "format_tanggal",
    )
    i, row = pick("workload_items")
    set_value(
        "workload_items",
        i,
        "received_date",
        _id_date(row["received_date"]).strftime("%Y/%m/%d"),
        "format_tanggal",
    )

    # Nilai enum di luar daftar.
    i, _ = pick("tasks", lambda r: r["status"] == "done")
    set_value("tasks", i, "status", "selesai", "enum")
    i, _ = pick("workload_items")
    set_value("workload_items", i, "severity", "urgent", "enum")

    # Referensi tidak dikenal.
    i, _ = pick("assignments")
    set_value("assignments", i, "resource_id", "RES-099", "fk_tidak_dikenal")
    i, _ = pick("change_events", lambda r: r["affected_task_id"] != "")
    set_value("change_events", i, "affected_task_id", "TSK-9999", "fk_tidak_dikenal")

    # Urutan tanggal terbalik.
    i, row = pick("availability")
    earlier = date.fromordinal(_id_date(row["date_start"]).toordinal() - 3).isoformat()
    set_value("availability", i, "date_end", earlier, "urutan_tanggal")

    # Format ID salah (baris tambahan).
    extra = dict(tables["availability"][0])
    extra["availability_id"] = "AVL-9"
    tables["availability"].append(extra)
    log.add(
        "final_sources",
        "availability.csv",
        "baris tambahan",
        "availability_id",
        "format_id",
        "",
        "AVL-9",
    )

    # Baris ganda.
    for table in ("tasks", "workload_items"):
        _, row = pick(table)
        tables[table].append(dict(row))
        log.add(
            "final_sources",
            f"{table}.csv",
            f"{ref.HEADERS[table][0]}={row[ref.HEADERS[table][0]]}",
            "*",
            "duplikat",
            "",
            "baris disalin",
        )

    # Siklus dependency: tambahkan arah balik dari dependency yang sudah ada.
    _, dep = pick("task_dependencies", lambda r: r["dependency_type"] == "hard")
    cycle = {
        "dependency_id": f"DEP-{len(tables['task_dependencies']) + 1:03d}",
        "task_id": dep["depends_on_task_id"],
        "depends_on_task_id": dep["task_id"],
        "dependency_type": "hard",
        "propagation_factor": "1.0",
    }
    tables["task_dependencies"].append(cycle)
    log.add(
        "final_sources",
        "task_dependencies.csv",
        f"dependency_id={cycle['dependency_id']}",
        "depends_on_task_id",
        "siklus_dependency",
        f"{dep['task_id']} bergantung pada {dep['depends_on_task_id']}",
        f"{cycle['task_id']} bergantung pada {cycle['depends_on_task_id']}",
    )
    return tables


# --------------------------------------------------------------------------- sumber mentah


def _pic_variants(name: str) -> list[str]:
    first, last = name.split()[0], name.split()[-1]
    return [first, name.upper(), f"{first.lower()} {last[0].lower()}", f"{first} {last}"]


def dirty_project_plans(world: World, rng: random.Random, log: _Defects) -> dict[str, list]:
    plans = copy.deepcopy(project_plan_rows(world))
    col = {name: index for index, name in enumerate(PLAN_HEADER)}
    names = {r.aliases["project_plan_pic"]: r.resource_name for r in world.resources}

    for project_id, rows in plans.items():
        file = f"project_plan_{project_id}.csv"
        dated = [r for r in rows if r[col["Mulai Rencana"]]]
        for row in rng.sample(dated, min(3, len(dated))):
            day, month, year = row[col["Mulai Rencana"]].split("/")
            value = rng.choice(
                [
                    f"{year}-{month}-{day}",
                    f"{int(day)} {_month(int(month))} {year}",
                    f"{int(day)}/{int(month)}/{year[2:]}",
                ]
            )
            log.add(
                "project_plan",
                file,
                f"Kode={row[col['Kode']]}",
                "Mulai Rencana",
                "format_tanggal",
                row[col["Mulai Rencana"]],
                value,
            )
            row[col["Mulai Rencana"]] = value
        with_pic = [r for r in rows if r[col["PIC"]] in names]
        for row in rng.sample(with_pic, min(2, len(with_pic))):
            value = rng.choice(_pic_variants(names[row[col["PIC"]]]))
            log.add(
                "project_plan",
                file,
                f"Kode={row[col['Kode']]}",
                "PIC",
                "alias_berbeda",
                row[col["PIC"]],
                value,
            )
            row[col["PIC"]] = value
        duplicate = list(rng.choice(rows))
        rows.append(duplicate)
        log.add(
            "project_plan",
            file,
            f"Kode={duplicate[col['Kode']]}",
            "*",
            "duplikat",
            "",
            "baris disalin",
        )
        target = rng.choice(rows[:-1])
        log.add(
            "project_plan",
            file,
            f"Kode={target[col['Kode']]}",
            "Estimasi (hari)",
            "wajib_kosong",
            target[col["Estimasi (hari)"]],
            "",
        )
        target[col["Estimasi (hari)"]] = ""

    # Siklus dependency di Project Plan PRJ-002: task awal dibuat bergantung pada task sesudahnya.
    rows = plans["PRJ-002"]
    first = rows[0]
    later = next(r for r in rows if first[col["Kode"]] in r[col["Bergantung Pada"]])
    added = f"{later[col['Kode']]} (hard)"
    before = first[col["Bergantung Pada"]]
    first[col["Bergantung Pada"]] = "; ".join(filter(None, [before, added]))
    log.add(
        "project_plan",
        "project_plan_PRJ-002.csv",
        f"Kode={first[col['Kode']]}",
        "Bergantung Pada",
        "siklus_dependency",
        before,
        first[col["Bergantung Pada"]],
    )

    # PIC yang tidak ada di daftar anggota.
    rows = plans["PRJ-003"]
    target = rng.choice([r for r in rows if r[col["PIC"]]])
    log.add(
        "project_plan",
        "project_plan_PRJ-003.csv",
        f"Kode={target[col['Kode']]}",
        "PIC",
        "fk_tidak_dikenal",
        target[col["PIC"]],
        "Dodi (magang)",
    )
    target[col["PIC"]] = "Dodi (magang)"
    return plans


def _month(month: int) -> str:
    return ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"][
        month - 1
    ]


def dirty_trello(world: World, rng: random.Random, log: _Defects) -> dict[str, object]:
    board = copy.deepcopy(trello_board(world))
    file = "trello_board.json"
    # Satu anggota punya dua akun Trello; sebagian kartu memakai akun kedua.
    original = board["members"][1]
    twin = {
        "id": "f" * 24,
        "fullName": original["fullName"].split()[0],
        "username": original["username"] + "2",
    }
    board["members"].append(twin)
    owned = [c for c in board["cards"] if original["id"] in c["idMembers"]]
    for card in rng.sample(owned, min(3, len(owned))):
        card["idMembers"] = [twin["id"] if m == original["id"] else m for m in card["idMembers"]]
        log.add(
            "trello",
            file,
            f"card={card['name'].split(' | ')[0]}",
            "idMembers",
            "alias_berbeda",
            original["username"],
            twin["username"],
        )
    # Kartu tanpa kode task.
    task_cards = [c for c in board["cards"] if c["name"].startswith("TSK-")]
    for card in rng.sample(task_cards, 2):
        before = card["name"]
        card["name"] = before.split(" | ", 1)[1]
        log.add(
            "trello",
            file,
            f"card.id={card['id']}",
            "name",
            "kode_task_hilang",
            before,
            card["name"],
        )
    # Aksi tercatat dua kali.
    action = rng.choice([a for a in board["actions"] if a["type"] == "updateCard"])
    board["actions"].append(copy.deepcopy(action))
    log.add("trello", file, f"action.id={action['id']}", "*", "duplikat", "", "aksi disalin")
    return board


def dirty_git(world: World, rng: random.Random, log: _Defects) -> dict[str, list]:
    commits = copy.deepcopy(git_commits(world))
    for project_id, entries in sorted(commits.items()):
        file = f"{project_id}.log"
        entry = rng.choice(entries)
        local = entry["email"].split("@")[0].split(".")[0]
        email = f"{local}{rng.randint(10, 99)}@gmail.example"
        log.add(
            "git",
            file,
            f"commit={entry['hash'][:8]}",
            "email",
            "alias_berbeda",
            entry["email"],
            email,
        )
        entry["email"] = email
        tagged = [e for e in entries if "[TSK-" in e["message"]]
        if tagged:
            entry = rng.choice(tagged)
            message = entry["message"].rsplit("[", 1)[0] + "[TSK-9999]"
            log.add(
                "git",
                file,
                f"commit={entry['hash'][:8]}",
                "message",
                "fk_tidak_dikenal",
                entry["message"],
                message,
            )
            entry["message"] = message
    return commits


# --------------------------------------------------------------------------- penulis


def write_dirty(world: World, out_dir: Path) -> dict[str, int]:
    rng = random.Random(world.seed + 10)
    log = _Defects()

    tables = dirty_final_sources(world, rng, log)
    final_dir = out_dir / "final_sources"
    final_dir.mkdir(parents=True, exist_ok=True)
    for table, rows in tables.items():
        with (final_dir / f"{table}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, ref.HEADERS[table], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    plans = dirty_project_plans(world, rng, log)
    plan_dir = out_dir / "raw" / "project_plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    for project_id, rows in plans.items():
        with (plan_dir / f"project_plan_{project_id}.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(PLAN_HEADER)
            writer.writerows(rows)

    board = dirty_trello(world, rng, log)
    (out_dir / "raw" / "trello").mkdir(parents=True, exist_ok=True)
    (out_dir / "raw" / "trello" / "trello_board.json").write_text(
        json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    commits = dirty_git(world, rng, log)
    (out_dir / "raw" / "git").mkdir(parents=True, exist_ok=True)
    for project_id, entries in sorted(commits.items()):
        (out_dir / "raw" / "git" / f"{project_id}.log").write_text(
            format_git_log(entries), encoding="utf-8"
        )

    with (out_dir / "manifest_cacat.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(MANIFEST_HEADER)
        writer.writerows(log.rows)
    counts: dict[str, int] = {}
    for row in log.rows:
        counts[row[4]] = counts.get(row[4], 0) + 1
    return dict(sorted(counts.items()))
