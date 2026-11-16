"""Aturan final sources D-01 s.d. D-11 (DIG-140, DIG-141, DIG-142, DIG-143).

Kolom, kolom wajib, FK, dan tipe diturunkan dari model (`app.modules.data.models`). Pola ID dan
enum diambil dari `app.modules.data.enums`. Tidak ada daftar yang disalin dari generator
(`synthetic/checks.py` hanya pembanding di tes).

Nomor aturan seragam antartabel (lihat docs/DATA_QUALITY_RULES.md):
001 wajib, 002 format ID, 003 enum, 004 FK, 005 PK ganda, 006 isi identik, 007 format tanggal,
008 tipe, 009 urutan tanggal, 010 aturan nilai CHECK, 011 dan seterusnya khusus tabel.
"""

import re
from collections.abc import Callable, Iterable
from enum import StrEnum

from sqlalchemy import Boolean, Date, Double, Integer

import app.modules.data.models  # noqa: F401  (mendaftarkan D-01 s.d. D-11 ke metadata)
from app.db.base import Base
from app.modules.data import enums
from app.modules.data.quality.cycles import Edge, resolve_cycles
from app.modules.data.quality.dates import ISO, parse_date
from app.modules.data.quality.engine import (
    PERINGATAN,
    TOLAK,
    Context,
    Hit,
    Report,
    Rule,
    SourceRow,
    Tables,
    register,
    run_rules,
)

TABLES = (
    "projects",
    "resources",
    "roles",
    "complexity_levels",
    "tasks",
    "task_dependencies",
    "assignments",
    "workload_items",
    "availability",
    "change_events",
    "holidays",
)
CODES = {
    "projects": "PRJ",
    "resources": "RES",
    "roles": "ROL",
    "complexity_levels": "CPX",
    "tasks": "TSK",
    "task_dependencies": "DEP",
    "assignments": "ASG",
    "workload_items": "WLI",
    "availability": "AVL",
    "change_events": "CHG",
    "holidays": "HOL",
}

ID_PATTERNS: dict[str, dict[str, str]] = {
    "projects": {"project_id": enums.PROJECT_ID_PATTERN},
    "resources": {
        "resource_id": enums.RESOURCE_ID_PATTERN,
        "secondary_role_ids": enums.SECONDARY_ROLE_IDS_PATTERN,
    },
    "roles": {"role_id": enums.ROLE_ID_PATTERN},
    "complexity_levels": {"complexity_id": enums.COMPLEXITY_ID_PATTERN},
    "tasks": {"task_id": enums.TASK_ID_PATTERN},
    "task_dependencies": {"dependency_id": enums.DEPENDENCY_ID_PATTERN},
    "assignments": {"assignment_id": enums.ASSIGNMENT_ID_PATTERN},
    "workload_items": {"item_id": enums.WORKLOAD_ITEM_ID_PATTERN},
    "availability": {"availability_id": enums.AVAILABILITY_ID_PATTERN},
    "change_events": {"event_id": enums.EVENT_ID_PATTERN},
}
ENUMS: dict[str, dict[str, type[StrEnum]]] = {
    "projects": {"status": enums.ProjectStatus},
    "resources": {"seniority": enums.Seniority},
    "tasks": {"phase": enums.TaskPhase, "status": enums.TaskStatus},
    "task_dependencies": {"dependency_type": enums.DependencyType},
    "workload_items": {"item_type": enums.WorkloadItemType, "severity": enums.Severity},
    "availability": {"absence_type": enums.AbsenceType},
    "change_events": {
        "event_type": enums.ChangeEventType,
        "decision": enums.Decision,
        "resolution_mode": enums.ResolutionMode,
    },
}
# Isi identik dengan PK berbeda (006) tidak berlaku untuk holidays (nama libur boleh berulang)
# dan task_dependencies (pasangan ganda sudah ditolak DEP-011).
NO_CONTENT_DUPLICATE = {"holidays", "task_dependencies"}

_INT = re.compile(r"^-?[0-9]+$")
_FLOAT = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
_BOOL = ("true", "false")


def _kind(column) -> str:
    if isinstance(column.type, Boolean):
        return "bool"
    if isinstance(column.type, Integer):
        return "int"
    if isinstance(column.type, Double):
        return "float"
    if isinstance(column.type, Date):
        return "date"
    return "text"


COLUMNS = {t: [c.name for c in Base.metadata.tables[t].columns] for t in TABLES}
PRIMARY_KEY = {t: Base.metadata.tables[t].primary_key.columns.keys()[0] for t in TABLES}
REQUIRED = {t: [c.name for c in Base.metadata.tables[t].columns if not c.nullable] for t in TABLES}
KINDS = {t: {c.name: _kind(c) for c in Base.metadata.tables[t].columns} for t in TABLES}
FOREIGN_KEYS = {
    t: [
        (c.name, next(iter(c.foreign_keys)).column.table.name)
        for c in Base.metadata.tables[t].columns
        if c.foreign_keys
    ]
    for t in TABLES
}

Check = Callable[[list[SourceRow], Context], Iterable[Hit]]


def rule(table: str, number: int, characteristic, level, text: str) -> Callable[[Check], Check]:
    """Daftarkan fungsi check sebagai aturan DQ-<TBL>-<nomor>."""

    def wrap(check: Check) -> Check:
        register(Rule(f"DQ-{CODES[table]}-{number:03d}", table, characteristic, level, text, check))
        return check

    return wrap


def blank(value: str | None) -> bool:
    return value is None or value.strip() == ""


def number(row: SourceRow, column: str) -> float | None:
    """Nilai numerik bila sel berformat bilangan sah, selain itu None (pelanggarannya di 008)."""
    value = row.values.get(column, "")
    return float(value) if _FLOAT.fullmatch(value) else None


def _where(row: SourceRow) -> str:
    return f"baris {row.number}" if row.number is not None else "baris sebelumnya"


# --------------------------------------------------------------------------- aturan umum


def _register_common(table: str) -> None:
    pk = PRIMARY_KEY[table]

    @rule(table, 1, "completeness", TOLAK, "Kolom wajib tidak kosong")
    def required(rows, ctx):
        for row in rows:
            for column in REQUIRED[table]:
                if blank(row.values.get(column)):
                    yield Hit(
                        row, column, row.values.get(column, ""), f"Kolom wajib {column} kosong"
                    )

    if table in ID_PATTERNS:

        @rule(table, 2, "consistency", TOLAK, "Format ID sesuai pola")
        def id_format(rows, ctx):
            for row in rows:
                for column, pattern in ID_PATTERNS[table].items():
                    value = row.values.get(column, "")
                    if value and not re.fullmatch(pattern, value):
                        yield Hit(row, column, value, f"Format {column} tidak sah: {value!r}")

    if table in ENUMS:

        @rule(table, 3, "consistency", TOLAK, "Nilai enum termasuk daftar nilai")
        def enum_value(rows, ctx):
            for row in rows:
                for column, allowed in ENUMS[table].items():
                    value = row.values.get(column, "")
                    if value and value not in {member.value for member in allowed}:
                        yield Hit(row, column, value, f"Nilai {column} {value!r} tidak dikenal")

    if FOREIGN_KEYS[table]:

        @rule(table, 4, "consistency", TOLAK, "Referensi FK dikenal")
        def foreign_key(rows, ctx):
            for row in rows:
                for column, target in FOREIGN_KEYS[table]:
                    value = row.values.get(column, "")
                    if value and value not in ctx.keys(target):
                        yield Hit(row, column, value, f"{column} {value} tidak ada di {target}")

    @rule(table, 5, "consistency", TOLAK, "PK tidak muncul dua kali")
    def duplicate_key(rows, ctx):
        first: dict[str, SourceRow] = {}
        for row in rows:
            key = row.values.get(pk, "")
            if not key:
                continue
            if key in first:
                same = dict(first[key].values) == dict(row.values)
                yield Hit(
                    row,
                    pk,
                    key,
                    f"{pk} {key} sudah muncul di {_where(first[key])}"
                    + (" dengan isi identik" if same else " dengan isi berbeda"),
                )
            else:
                first[key] = row

    if table not in NO_CONTENT_DUPLICATE:

        @rule(table, 6, "consistency", PERINGATAN, "Isi baris identik dengan PK berbeda")
        def duplicate_content(rows, ctx):
            first: dict[tuple, SourceRow] = {}
            for row in rows:
                content = tuple(row.values.get(c, "") for c in COLUMNS[table] if c != pk)
                if all(blank(v) for v in content):
                    continue
                seen = first.setdefault(content, row)
                if seen is not row and seen.values.get(pk) != row.values.get(pk):
                    yield Hit(row, None, None, f"Isi sama dengan {pk} {seen.values.get(pk)}")

    typed = {c: k for c, k in KINDS[table].items() if k in ("int", "float", "bool")}
    if typed:

        @rule(table, 8, "consistency", TOLAK, "Tipe bilangan atau boolean sesuai Data Dictionary")
        def value_type(rows, ctx):
            pattern = {"int": _INT, "float": _FLOAT}
            for row in rows:
                for column, kind in typed.items():
                    value = row.values.get(column, "")
                    if not value:
                        continue
                    ok = value in _BOOL if kind == "bool" else pattern[kind].fullmatch(value)
                    if not ok:
                        expected = {
                            "int": "bilangan bulat",
                            "float": "desimal bertitik",
                            "bool": "true/false",
                        }[kind]
                        yield Hit(row, column, value, f"{column} {value!r} bukan {expected}")


for _table in TABLES:
    _register_common(_table)


# --------------------------------------------------------------------------- 010 aturan nilai

# (tabel, kolom, syarat, keterangan). Syarat menerima fungsi pembaca angka dan baris.
VALUE_RULES: dict[str, list[tuple[str, Callable[[Callable, SourceRow], bool], str]]] = {
    "projects": [("priority_rank", lambda n, r: n(r, "priority_rank") >= 1, "harus >= 1")],
    "roles": [("capacity_reference", lambda n, r: n(r, "capacity_reference") > 0, "harus > 0")],
    "complexity_levels": [
        ("min_days", lambda n, r: n(r, "min_days") >= 0, "harus >= 0"),
        ("max_days", lambda n, r: n(r, "max_days") >= n(r, "min_days"), "harus >= min_days"),
        ("load_weight", lambda n, r: n(r, "load_weight") >= 0, "harus >= 0"),
    ],
    "tasks": [
        ("priority_rank", lambda n, r: n(r, "priority_rank") >= 1, "harus >= 1"),
        ("estimated_days", lambda n, r: n(r, "estimated_days") > 0, "harus > 0"),
        ("qa_reject_count", lambda n, r: n(r, "qa_reject_count") >= 0, "harus >= 0"),
    ],
    "task_dependencies": [
        (
            "propagation_factor",
            lambda n, r: 0 < n(r, "propagation_factor") <= 1,
            "harus lebih dari 0 dan paling besar 1",
        ),
        (
            "propagation_factor",
            lambda n, r: (
                r.values.get("dependency_type") != "hard" or n(r, "propagation_factor") == 1.0
            ),
            "harus 1.0 untuk dependency hard",
        ),
    ],
    "change_events": [("extension_days", lambda n, r: n(r, "extension_days") >= 0, "harus >= 0")],
}


def _register_values(table: str) -> None:
    @rule(table, 10, "consistency", TOLAK, "Aturan nilai yang juga dijaga CHECK basis data")
    def values(rows, ctx):
        for row in rows:
            for column, condition, explanation in VALUE_RULES.get(table, []):
                try:
                    ok = condition(number, row)
                except TypeError:  # sel kosong atau bukan angka: sudah dicatat 001/008
                    continue
                if not ok:
                    yield Hit(row, column, row.values.get(column), f"{column} {explanation}")
            if table == "task_dependencies":
                task, depends_on = row.values.get("task_id"), row.values.get("depends_on_task_id")
                if task and task == depends_on:
                    yield Hit(
                        row,
                        "depends_on_task_id",
                        depends_on,
                        "Task bergantung pada dirinya sendiri",
                    )


for _table in VALUE_RULES:
    _register_values(_table)


# --------------------------------------------------------------------------- tanggal (DIG-141)

# Kolom akhir tidak boleh lebih awal dari kolom awal (kontrak bagian 6, ck_*_after_*).
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


def day(row: SourceRow, column: str):
    """Tanggal ISO yang terbaca, atau None (kosong atau salah format, dicatat 001/007)."""
    return parse_date(row.values.get(column), ISO)


def _register_dates(table: str) -> None:
    columns = [c for c, kind in KINDS[table].items() if kind == "date"]
    if not columns:
        return

    @rule(table, 7, "consistency", TOLAK, "Tanggal berformat YYYY-MM-DD")
    def date_format(rows, ctx):
        for row in rows:
            for column in columns:
                value = row.values.get(column, "")
                if value and parse_date(value, ISO) is None:
                    yield Hit(row, column, value, f"{column} {value!r} bukan tanggal {ISO.label}")

    pairs = [(start, end) for t, start, end in DATE_ORDER if t == table]
    if not pairs:
        return

    @rule(table, 9, "consistency", TOLAK, "Tanggal akhir tidak lebih awal dari tanggal awal")
    def date_order(rows, ctx):
        for row in rows:
            for start, end in pairs:
                first, last = day(row, start), day(row, end)
                if first and last and last < first:
                    yield Hit(
                        row, end, row.values[end], f"{end} {last} lebih awal dari {start} {first}"
                    )


for _table in TABLES:
    _register_dates(_table)


@rule("tasks", 11, "consistency", TOLAK, "actual_finish butuh actual_start")
def finish_needs_start(rows, ctx):
    for row in rows:
        if not blank(row.values.get("actual_finish")) and blank(row.values.get("actual_start")):
            yield Hit(row, "actual_start", "", "actual_finish terisi tetapi actual_start kosong")


@rule("tasks", 12, "consistency", PERINGATAN, "Tanggal rencana tidak jatuh di hari libur")
def planned_on_holiday(rows, ctx):
    for row in rows:
        for column in ("planned_start", "planned_finish"):
            if (value := day(row, column)) and value in ctx.holidays:
                yield Hit(row, column, row.values[column], f"{column} {value} jatuh di hari libur")


@rule("tasks", 13, "consistency", PERINGATAN, "estimated_days dalam rentang level kompleksitasnya")
def estimate_in_range(rows, ctx):
    for row in rows:
        estimate = number(row, "estimated_days")
        bounds = ctx.complexity_ranges.get(row.values.get("complexity_id", ""))
        if estimate is not None and bounds and not bounds[0] <= estimate <= bounds[1]:
            yield Hit(
                row,
                "estimated_days",
                row.values["estimated_days"],
                f"estimated_days {estimate:g} di luar {bounds[0]:g} s.d. {bounds[1]:g} hari "
                f"untuk {row.values['complexity_id']}",
            )


# --------------------------------------------------------------------------- khusus tabel


@rule(
    "task_dependencies",
    11,
    "consistency",
    TOLAK,
    "Pasangan task_id dan depends_on_task_id tidak ganda",
)
def duplicate_pair(rows, ctx):
    first: dict[tuple[str, str], SourceRow] = {}
    for row in rows:
        pair = (row.values.get("task_id", ""), row.values.get("depends_on_task_id", ""))
        if not all(pair):
            continue
        seen = first.setdefault(pair, row)
        if seen is not row:
            yield Hit(
                row,
                "depends_on_task_id",
                pair[1],
                f"{pair[0]} bergantung pada {pair[1]} sudah dicatat "
                f"{seen.values.get('dependency_id')}",
            )


# --------------------------------------------------------------------------- siklus (DIG-142)


def _cycles(rows: list[SourceRow]):
    edges = [
        Edge(
            row.values.get("dependency_id", ""),
            row.values.get("task_id", ""),
            row.values.get("depends_on_task_id", ""),
        )
        for row in rows
    ]
    return resolve_cycles(edges)


@rule("task_dependencies", 12, "consistency", TOLAK, "Dependency tidak menutup siklus")
def closing_edge(rows, ctx):
    for cycle in _cycles(rows):
        row = rows[cycle.closing]
        yield Hit(
            row,
            "depends_on_task_id",
            row.values.get("depends_on_task_id"),
            "Menutup siklus " + " -> ".join(cycle.path),
        )


@rule("task_dependencies", 13, "consistency", PERINGATAN, "Dependency bukan bagian siklus")
def cycle_member(rows, ctx):
    closing = set()
    members: dict[int, str] = {}
    for cycle in _cycles(rows):
        closing.add(cycle.closing)
        for index in cycle.members:
            members.setdefault(index, rows[cycle.closing].values.get("dependency_id", ""))
    for index, closer in members.items():
        if index not in closing:
            row = rows[index]
            yield Hit(
                row,
                "depends_on_task_id",
                row.values.get("depends_on_task_id"),
                f"Bagian dari siklus yang ditutup {closer}",
            )


# --------------------------------------------------------------------------- validasi


def completeness(tables: Tables) -> dict[str, tuple[int, int]]:
    """Per tabel: (sel wajib terisi, seluruh sel wajib)."""
    result = {}
    for table in TABLES:
        if table not in tables:
            continue
        rows, required = tables[table], REQUIRED[table]
        filled = sum(not blank(row.values.get(c)) for row in rows for c in required)
        result[table] = (filled, len(rows) * len(required))
    return result


def validate_final_sources(tables: Tables, source: str = "final_sources") -> Report:
    """Jalankan semua aturan final sources atas dataset `tables` (tabel -> baris)."""
    present = {t: tables[t] for t in TABLES if t in tables}
    report = run_rules(present, source)
    report.completeness = completeness(present)
    return report
