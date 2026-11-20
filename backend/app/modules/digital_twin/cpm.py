"""Critical Path Method dan propagasi dampak keterlambatan (DIG-42, DIG-181).

Murni, tanpa basis data, supaya mudah dites (DIG-185) dan bisa dipakai ulang oleh simulasi.

Model yang dipakai:
- Durasi task = `estimated_days` (hari kerja). Jadwal CPM dihitung dalam hari kerja relatif
  terhadap awal proyek (hari ke-0), bukan tanggal kalender.
- Jalur kritis hanya mengikuti dependency `hard` (D-06: blokir total). Dependency `soft`
  berarti task turunan bisa dikerjakan sebagian lebih dulu, jadi tidak menahan jadwal mulai.
- Dampak keterlambatan merambat lewat semua dependency: dampak ke task turunan =
  dampak task prasyarat x `propagation_factor` (1,0 untuk hard, bawaan 0,3 untuk soft).
  Bila ada beberapa jalur, diambil dampak terbesar. Task yang sudah done atau dropped tidak
  terdampak dan tidak meneruskan dampak.
"""

from collections import defaultdict
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass

EPSILON = 1e-9


@dataclass(frozen=True)
class Edge:
    """`task_id` bergantung pada `depends_on` (arah kerja: depends_on lalu task_id)."""

    depends_on: str
    task_id: str
    hard: bool
    factor: float


@dataclass(frozen=True)
class Schedule:
    """Jadwal CPM satu task dalam hari kerja relatif terhadap awal proyek."""

    earliest_start: float
    earliest_finish: float
    latest_start: float
    latest_finish: float

    @property
    def total_float(self) -> float:
        return self.latest_start - self.earliest_start

    @property
    def is_critical(self) -> bool:
        return self.total_float <= EPSILON


class CycleError(ValueError):
    """Dependency membentuk lingkaran, jadi urutan kerja tidak bisa ditentukan."""

    def __init__(self, task_ids: list[str]) -> None:
        super().__init__(f"Dependency melingkar pada task: {', '.join(task_ids)}")
        self.task_ids = task_ids


def topological_order(task_ids: Iterable[str], edges: Iterable[Edge]) -> list[str]:
    """Urutan task sehingga setiap prasyarat muncul sebelum task yang bergantung padanya.

    Edge ke task yang tidak ada di `task_ids` diabaikan. Urutan stabil menurut ID.
    """
    nodes = sorted(set(task_ids))
    known = set(nodes)
    successors: dict[str, list[str]] = defaultdict(list)
    waiting = dict.fromkeys(nodes, 0)
    for edge in edges:
        if edge.depends_on in known and edge.task_id in known:
            successors[edge.depends_on].append(edge.task_id)
            waiting[edge.task_id] += 1
    ready = [node for node in nodes if waiting[node] == 0]
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for successor in sorted(successors[node]):
            waiting[successor] -= 1
            if waiting[successor] == 0:
                ready.append(successor)
    if len(order) != len(nodes):
        raise CycleError(sorted(node for node in nodes if waiting[node] > 0))
    return order


def critical_path(durations: Mapping[str, float], edges: Collection[Edge]) -> dict[str, Schedule]:
    """Jadwal CPM tiap task. Hanya dependency hard yang menahan jadwal.

    Task dengan `is_critical` membentuk jalur kritis: keterlambatannya langsung menggeser
    selesainya proyek. Melempar `CycleError` bila dependency hard melingkar.
    """
    hard = [e for e in edges if e.hard and e.depends_on in durations and e.task_id in durations]
    order = topological_order(durations, hard)
    predecessors: dict[str, list[str]] = defaultdict(list)
    successors: dict[str, list[str]] = defaultdict(list)
    for edge in hard:
        predecessors[edge.task_id].append(edge.depends_on)
        successors[edge.depends_on].append(edge.task_id)

    start: dict[str, float] = {}
    finish: dict[str, float] = {}
    for task in order:
        start[task] = max((finish[p] for p in predecessors[task]), default=0.0)
        finish[task] = start[task] + durations[task]
    project_finish = max(finish.values(), default=0.0)

    schedules: dict[str, Schedule] = {}
    latest_start: dict[str, float] = {}
    for task in reversed(order):
        latest_finish = min((latest_start[s] for s in successors[task]), default=project_finish)
        latest_start[task] = latest_finish - durations[task]
        schedules[task] = Schedule(start[task], finish[task], latest_start[task], latest_finish)
    return schedules


def propagate_delay(
    source: str,
    delay: float,
    edges: Collection[Edge],
    finished: Collection[str] = (),
) -> dict[str, float]:
    """Estimasi dampak (hari) ke task turunan bila `source` terlambat `delay` hari.

    Mengembalikan {task_id: dampak} untuk turunan yang terdampak, tanpa `source` sendiri.
    `finished` = task yang sudah done atau dropped. Melempar `CycleError` bila dependency
    melingkar.
    """
    if delay <= 0:
        return {}
    nodes = {source} | {e.depends_on for e in edges} | {e.task_id for e in edges}
    order = topological_order(nodes, edges)
    outgoing: dict[str, list[Edge]] = defaultdict(list)
    for edge in edges:
        outgoing[edge.depends_on].append(edge)
    stopped = set(finished) - {source}

    impact: dict[str, float] = {source: float(delay)}
    for task in order:
        current = impact.get(task)
        if current is None:
            continue
        for edge in outgoing[task]:
            if edge.task_id in stopped:
                continue
            passed = current * edge.factor
            if passed > impact.get(edge.task_id, 0.0):
                impact[edge.task_id] = passed
    del impact[source]
    return impact
