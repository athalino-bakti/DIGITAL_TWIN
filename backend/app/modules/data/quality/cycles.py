"""Deteksi siklus task_dependencies (DIG-142).

Graf memakai dependency hard dan soft. Critical path di modul CPM hanya mengikuti hard, tetapi
propagasi keterlambatan memakai keduanya, sehingga siklus soft pun membuat urutan task tidak
bisa ditentukan.

Penyelesaian: selama masih ada siklus, edge dengan `dependency_id` terbesar di siklus itu (yang
paling akhir ditambahkan) dicatat sebagai edge penutup dan dibuang dari graf. Edge lain di
siklus yang sama dilaporkan sebagai anggota siklus. Hasilnya deterministik karena simpul dan
edge selalu ditelusuri dalam urutan tetap.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

_NUMBER = re.compile(r"([0-9]+)$")


@dataclass(frozen=True)
class Edge:
    edge_id: str  # dependency_id
    task_id: str  # task yang bergantung
    depends_on: str  # task prasyarat


@dataclass(frozen=True)
class Cycle:
    closing: int  # indeks edge penutup di daftar edge masukan
    members: tuple[int, ...]  # indeks semua edge di siklus, termasuk penutup
    path: tuple[str, ...]  # task di siklus, berakhir di task awal


def id_order(edge: Edge) -> tuple[int, str]:
    """Urutan dependency_id menurut angkanya (DEP-99 sebelum DEP-154), lalu teksnya."""
    match = _NUMBER.search(edge.edge_id)
    return (int(match.group(1)) if match else -1, edge.edge_id)


def _find_cycle(edges: Sequence[Edge], active: set[int]) -> list[int] | None:
    """Indeks edge yang membentuk satu siklus di graf `active`, atau None bila acyclic."""
    successors: dict[str, list[int]] = defaultdict(list)
    for index in sorted(active, key=lambda i: (edges[i].depends_on, id_order(edges[i]))):
        successors[edges[index].task_id].append(index)
    state: dict[str, int] = {}  # 1 = sedang ditelusuri, 2 = selesai
    for start in sorted(successors):
        if start in state:
            continue
        state[start] = 1
        path: list[int] = []  # edge dari start ke simpul saat ini
        stack = [(start, iter(successors[start]))]
        while stack:
            node, pending = stack[-1]
            index = next(pending, None)
            if index is None:
                state[node] = 2
                stack.pop()
                if path:
                    path.pop()
                continue
            target = edges[index].depends_on
            if state.get(target) == 1:
                # Siklus: edge sejak keluar dari `target` sampai edge ini.
                begin = next(i for i, e in enumerate(path) if edges[e].task_id == target)
                return path[begin:] + [index]
            if target not in state:
                state[target] = 1
                path.append(index)
                stack.append((target, iter(successors[target])))
    return None


def resolve_cycles(edges: Sequence[Edge]) -> list[Cycle]:
    """Setiap siklus yang ditemukan beserta edge penutupnya. Self-dependency diabaikan (DEP-010)."""
    active = {
        i for i, e in enumerate(edges) if e.task_id and e.depends_on and e.task_id != e.depends_on
    }
    cycles = []
    while (members := _find_cycle(edges, active)) is not None:
        closing = max(members, key=lambda i: id_order(edges[i]))
        path = (*(edges[i].task_id for i in members), edges[members[0]].task_id)
        cycles.append(Cycle(closing, tuple(members), path))
        active.discard(closing)
    return cycles
