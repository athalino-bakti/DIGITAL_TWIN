"""Pemeriksaan mandiri keluaran generator terhadap aturan Data Dictionary.

Dipakai tes untuk memastikan data bersih lolos dan data kotor memang memuat cacat.
Ini bukan validator aplikasi (DIG-31); aturannya sengaja sederhana dan setara dengan
constraint basis data DIG-15.
"""

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

from synthetic import reference as ref

NULLABLE = {
    "projects": {"actual_launch_date"},
    "resources": {"secondary_role_ids"},
    "roles": {"description"},
    "tasks": {"actual_start", "actual_finish"},
    "assignments": {"released_date"},
    "workload_items": {"related_project_id", "started_date", "resolved_date", "severity"},
    "change_events": {
        "requested_by",
        "decision",
        "resolution_mode",
        "affected_task_id",
        "extension_days",
    },
}

FOREIGN_KEYS = [
    ("resources", "primary_role_id", "roles", "role_id"),
    ("tasks", "project_id", "projects", "project_id"),
    ("tasks", "required_role_id", "roles", "role_id"),
    ("tasks", "complexity_id", "complexity_levels", "complexity_id"),
    ("task_dependencies", "task_id", "tasks", "task_id"),
    ("task_dependencies", "depends_on_task_id", "tasks", "task_id"),
    ("assignments", "task_id", "tasks", "task_id"),
    ("assignments", "resource_id", "resources", "resource_id"),
    ("assignments", "role_in_task", "roles", "role_id"),
    ("workload_items", "resource_id", "resources", "resource_id"),
    ("workload_items", "related_project_id", "projects", "project_id"),
    ("availability", "resource_id", "resources", "resource_id"),
    ("change_events", "project_id", "projects", "project_id"),
    ("change_events", "affected_task_id", "tasks", "task_id"),
]

DATE_ORDER = [
    ("projects", "start_date", "target_launch_date"),
    ("projects", "start_date", "actual_launch_date"),
    ("tasks", "planned_start", "planned_finish"),
    ("tasks", "actual_start", "actual_finish"),
    ("assignments", "assigned_date", "released_date"),
    ("workload_items", "received_date", "started_date"),
    ("workload_items", "received_date", "resolved_date"),
    ("workload_items", "started_date", "resolved_date"),
    ("availability", "date_start", "date_end"),
]

PRIMARY_KEYS = {table: columns[0] for table, columns in ref.HEADERS.items()}


def read_tables(directory: Path) -> dict[str, list[dict[str, str]]]:
    tables = {}
    for table in ref.HEADERS:
        with (directory / f"{table}.csv").open(encoding="utf-8", newline="") as handle:
            tables[table] = list(csv.DictReader(handle))
    return tables


def _iso(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def find_problems(directory: Path) -> list[tuple[str, str, str]]:
    """Daftar (jenis, tabel, keterangan) untuk setiap pelanggaran aturan."""
    problems: list[tuple[str, str, str]] = []
    tables = read_tables(directory)
    for table, rows in tables.items():
        with (directory / f"{table}.csv").open(encoding="utf-8") as handle:
            header = handle.readline().strip().split(",")
        if header != ref.HEADERS[table]:
            problems.append(("header", table, f"kolom {header}"))
        pk = PRIMARY_KEYS[table]
        seen: set[str] = set()
        for index, row in enumerate(rows, start=2):
            where = f"baris {index}"
            if row[pk] in seen:
                problems.append(("duplikat", table, f"{where}: {pk}={row[pk]}"))
            seen.add(row[pk])
            for column in ref.HEADERS[table]:
                value = row[column]
                if value == "" and column not in NULLABLE.get(table, set()):
                    problems.append(("wajib_kosong", table, f"{where}: {column}"))
                    continue
                pattern = ref.ID_PATTERNS.get(column)
                if pattern and value and column == pk and not pattern.match(value):
                    problems.append(("format_id", table, f"{where}: {column}={value}"))
                allowed = ref.ENUMS.get((table, column))
                if allowed and value and value not in allowed:
                    problems.append(("enum", table, f"{where}: {column}={value}"))
                if value and (
                    column.endswith("_date") or column.startswith(("planned_", "actual_"))
                ):
                    if column != "actual_launch_date" or value:
                        if _iso(value) is None:
                            problems.append(("format_tanggal", table, f"{where}: {column}={value}"))
            for first, second in [(a, b) for t, a, b in DATE_ORDER if t == table]:
                start, end = _iso(row[first]), _iso(row[second])
                if start and end and end < start:
                    problems.append(("urutan_tanggal", table, f"{where}: {second} < {first}"))
    for table, column, target, target_column in FOREIGN_KEYS:
        keys = {row[target_column] for row in tables[target]}
        for index, row in enumerate(tables[table], start=2):
            if row[column] and row[column] not in keys:
                problems.append(
                    ("fk_tidak_dikenal", table, f"baris {index}: {column}={row[column]}")
                )
    problems.extend(("siklus_dependency", "task_dependencies", c) for c in _cycles(tables))
    return problems


def _cycles(tables: dict[str, list[dict[str, str]]]) -> list[str]:
    graph: dict[str, list[str]] = defaultdict(list)
    for row in tables["task_dependencies"]:
        graph[row["task_id"]].append(row["depends_on_task_id"])
    state: dict[str, int] = {}
    found: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                found.append(" -> ".join(path[path.index(nxt) :] + [nxt]))
            elif nxt not in state:
                visit(nxt, path + [nxt])
        state[node] = 2

    for node in sorted(graph):
        if node not in state:
            visit(node, [node])
    return found
