"""Directly-follows graph (DFG) dari event log untuk tab Process Map (DIG-168, story DIG-38).

Murni, tanpa basis data dan tanpa pustaka process mining, supaya mudah dites dan dibandingkan
dengan pm4py atau ProM.

- Trace = event satu case (task) terurut waktu. Pasangan berurutan a lalu b dalam satu trace
  menjadi satu kemunculan edge a -> b; pasangan dengan aktivitas sama (a -> a) tetap dihitung.
- Node menghitung jumlah event, jumlah case yang memuatnya, serta berapa case diawali dan
  diakhiri aktivitas itu. Case berisi satu event tidak punya edge, tetapi tetap dihitung
  sebagai awal sekaligus akhir.
- Durasi edge = selisih waktu kedua event dalam jam; dilaporkan rata-rata dan median.
"""

import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True)
class Step:
    """Satu event dalam trace."""

    activity: str
    time: datetime


@dataclass(frozen=True)
class Node:
    activity: str
    frequency: int
    cases: int
    start_cases: int
    end_cases: int


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    frequency: int
    cases: int
    mean_hours: float
    median_hours: float


@dataclass(frozen=True)
class Hidden:
    """Yang disembunyikan filter frekuensi, untuk keterangan di tampilan."""

    edges: int = 0
    nodes: int = 0
    edge_frequency: int = 0


@dataclass(frozen=True)
class ProcessMap:
    nodes: list[Node]
    edges: list[Edge]
    cases: int
    events: int
    # Dihitung sebelum filter, sebagai batas atas slider frekuensi.
    max_edge_frequency: int


def _hours(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 3600


def directly_follows(traces: Mapping[str, Sequence[Step]]) -> ProcessMap:
    """DFG dari trace per case. Setiap trace harus sudah terurut waktu."""
    frequency: Counter[str] = Counter()
    node_cases: Counter[str] = Counter()
    starts: Counter[str] = Counter()
    ends: Counter[str] = Counter()
    gaps: dict[tuple[str, str], list[float]] = defaultdict(list)
    edge_cases: Counter[tuple[str, str]] = Counter()
    cases = 0

    for steps in traces.values():
        if not steps:
            continue
        cases += 1
        starts[steps[0].activity] += 1
        ends[steps[-1].activity] += 1
        frequency.update(step.activity for step in steps)
        node_cases.update({step.activity for step in steps})
        pairs = set()
        for before, after in zip(steps, steps[1:]):
            key = (before.activity, after.activity)
            gaps[key].append(_hours(before.time, after.time))
            pairs.add(key)
        edge_cases.update(pairs)

    nodes = [
        Node(activity, count, node_cases[activity], starts[activity], ends[activity])
        for activity, count in frequency.items()
    ]
    edges = [
        Edge(
            source,
            target,
            len(values),
            edge_cases[(source, target)],
            round(statistics.fmean(values), 2),
            round(statistics.median(values), 2),
        )
        for (source, target), values in gaps.items()
    ]
    nodes.sort(key=lambda n: (-n.frequency, n.activity))
    edges.sort(key=lambda e: (-e.frequency, e.source, e.target))
    return ProcessMap(
        nodes=nodes,
        edges=edges,
        cases=cases,
        events=sum(frequency.values()),
        max_edge_frequency=max((e.frequency for e in edges), default=0),
    )


def filter_by_frequency(pm: ProcessMap, min_frequency: int) -> tuple[ProcessMap, Hidden]:
    """Sembunyikan edge dengan frekuensi di bawah ambang, lalu node yang jadi yatim.

    Node tetap tampil bila frekuensinya sendiri memenuhi ambang, walau semua edge-nya hilang.
    """
    kept = [e for e in pm.edges if e.frequency >= min_frequency]
    linked = {e.source for e in kept} | {e.target for e in kept}
    nodes = [n for n in pm.nodes if n.frequency >= min_frequency or n.activity in linked]
    hidden_edges = [e for e in pm.edges if e.frequency < min_frequency]
    hidden = Hidden(
        edges=len(hidden_edges),
        nodes=len(pm.nodes) - len(nodes),
        edge_frequency=sum(e.frequency for e in hidden_edges),
    )
    return replace(pm, nodes=nodes, edges=kept), hidden
