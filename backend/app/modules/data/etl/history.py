"""Derivasi `actual_start`, `actual_finish`, dan `qa_reject_count` dari riwayat Trello (DIG-132).

Fungsi murni di atas `TrelloMove` (lihat `normalize`) dan `trello_list_mapping`. Hanya list yang
sudah dipetakan ke status yang dihitung; list belum dipetakan dilewati.

Aturan (RANCANGAN_ETL_DIG-29.md bagian 2, AC DIG-29):
- `actual_start`: tanggal WIB pertama kartu masuk list berstatus mulai (`in_progress`, `blocked`,
  `in_qa`, atau `done`). Kartu yang langsung dipindah ke QA atau Done tetap dianggap mulai saat
  itu. Hanya mengisi bila Project Plan kosong.
- `actual_finish`: tanggal WIB terakhir kartu masuk list berstatus `done`, dan hanya bila status
  terakhir kartu memang `done` (kartu yang dibuka lagi tidak punya tanggal selesai). Hanya
  mengisi bila Project Plan kosong.
- `qa_reject_count`: jumlah perpindahan dari list `in_qa` langsung ke list `in_progress` atau
  `blocked`, yaitu task dikembalikan dari QA ke pengembangan. Selalu dari Trello; task tanpa
  kartu tetap 0.
- Derivasi dari commit TeamGit menyusul DIG-27 (keputusan Davi 24 Nov).
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

from app.modules.data.enums import TaskStatus
from app.modules.data.etl.normalize import Candidates, TrelloMove, to_wib_date
from app.modules.data.event_log import task_id_from_card

STARTED = frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.IN_QA, TaskStatus.DONE})
REWORK = frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED})


@dataclass(frozen=True)
class History:
    actual_start: str  # ISO atau ""
    actual_finish: str
    qa_reject_count: int


def derive_history(
    moves: Iterable[TrelloMove], mapping: Mapping[tuple[str, str], tuple[str | None, str | None]]
) -> dict[str, History]:
    """{task_id: History} dari aksi Trello yang menaruh kartu di sebuah list."""
    timeline: dict[str, list[tuple[TaskStatus, TrelloMove]]] = defaultdict(list)
    for move in sorted(moves, key=lambda m: m.at):
        task_id = task_id_from_card(move.card_name)
        status = mapping.get((move.board_id, move.list_id), (None, None))[0]
        if task_id and status:
            timeline[task_id].append((TaskStatus(status), move))

    result = {}
    for task_id, steps in timeline.items():
        started = next((m.at for s, m in steps if s in STARTED), None)
        finished = next((m.at for s, m in reversed(steps) if s is TaskStatus.DONE), None)
        if steps[-1][0] is not TaskStatus.DONE:
            finished = None
        rejects = sum(
            1
            for (before, _), (after, _) in zip(steps, steps[1:], strict=False)
            if before is TaskStatus.IN_QA and after in REWORK
        )
        result[task_id] = History(
            to_wib_date(started).isoformat() if started else "",
            to_wib_date(finished).isoformat() if finished else "",
            rejects,
        )
    return result


def apply_history(candidates: Candidates, history: Mapping[str, History]) -> Candidates:
    """Isi kolom turunan kandidat `tasks`. Nilai Project Plan yang sudah ada tidak ditimpa."""
    rows = []
    for row in candidates.tables["tasks"]:
        found = history.get(row.values.get("task_id", ""))
        if found is None:
            rows.append(row)
            continue
        values = dict(row.values)
        values["actual_start"] = values.get("actual_start") or found.actual_start
        values["actual_finish"] = values.get("actual_finish") or found.actual_finish
        values["qa_reject_count"] = str(found.qa_reject_count)
        rows.append(replace(row, values=values))
    return Candidates(
        tables={**candidates.tables, "tasks": rows}, problems=list(candidates.problems)
    )
