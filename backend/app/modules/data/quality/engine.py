"""Mesin aturan kualitas data (DIG-140).

Setiap aturan adalah fungsi murni atas baris sumber (teks apa adanya) ditambah konteks dari
dataset yang sama. Aturan tidak mengubah nilai dan tidak menulis ke basis data.

Keluaran `Report` disusun supaya bisa langsung disimpan DIG-145:
- `summaries`: satu baris per aturan per sumber (diperiksa, melanggar) untuk
  `data_quality_result`;
- `rejected_rows()`: baris bertemuan `tolak` beserta alasannya untuk `rejected_row`;
- `findings`: semua temuan, termasuk peringatan.
"""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from typing import Any, Literal

from app.modules.data.quality.dates import ISO, parse_date

Level = Literal["tolak", "peringatan"]
Characteristic = Literal["completeness", "consistency", "currentness", "traceability"]
TOLAK: Level = "tolak"
PERINGATAN: Level = "peringatan"


@dataclass(frozen=True)
class SourceRow:
    """Satu baris sumber. `number` = nomor baris berkas (judul kolom = 1), None untuk basis data."""

    number: int | None
    key: str | None  # nilai PK bila ada
    values: Mapping[str, str]  # kolom -> teks apa adanya; "" = kosong


Tables = Mapping[str, list[SourceRow]]


@dataclass(frozen=True)
class Hit:
    """Pelanggaran yang ditemukan sebuah aturan pada satu baris."""

    row: SourceRow
    column: str | None
    value: str | None
    message: str


@dataclass(frozen=True)
class Rule:
    rule_id: str
    table: str
    characteristic: Characteristic
    level: Level
    text: str
    # None untuk aturan yang tidak berbasis baris (currentness), dihitung modulnya sendiri.
    check: Callable[[list[SourceRow], "Context"], Iterable[Hit]] | None = None


@dataclass(frozen=True)
class Finding:
    rule_id: str
    characteristic: str
    level: str
    source: str
    table: str
    row_number: int | None
    row_key: str | None
    column: str | None
    value: str | None
    message: str


@dataclass(frozen=True)
class RuleSummary:
    rule_id: str
    source: str
    table: str
    characteristic: str
    level: str
    text: str
    checked: int
    violated: int


@dataclass
class Report:
    source: str
    findings: list[Finding] = field(default_factory=list)
    summaries: list[RuleSummary] = field(default_factory=list)
    # tabel -> (sel wajib terisi, seluruh sel wajib)
    completeness: dict[str, tuple[int, int]] = field(default_factory=dict)
    currentness: list[dict[str, Any]] = field(default_factory=list)

    def rejected_rows(self) -> list[dict[str, Any]]:
        """Baris bertemuan tolak, satu entri per baris beserta semua alasannya."""
        rows: dict[tuple, dict[str, Any]] = {}
        for item in self.findings:
            if item.level != TOLAK:
                continue
            key = (item.table, item.row_number, item.row_key)
            entry = rows.setdefault(
                key,
                {
                    "source": item.source,
                    "table": item.table,
                    "row_number": item.row_number,
                    "row_key": item.row_key,
                    "rule_ids": [],
                    "reasons": [],
                },
            )
            entry["rule_ids"].append(item.rule_id)
            entry["reasons"].append(item.message)
        return list(rows.values())

    def completeness_score(self, table: str | None = None) -> float | None:
        """Pecahan sel wajib terisi per tabel, atau keseluruhan bila `table` None."""
        pairs = [self.completeness[table]] if table else list(self.completeness.values())
        filled, total = sum(p[0] for p in pairs), sum(p[1] for p in pairs)
        return filled / total if total else None


class Context:
    """Data rujukan yang diturunkan dari dataset yang sama, dihitung sekali bila dibutuhkan."""

    def __init__(self, tables: Tables) -> None:
        self.tables = tables

        self._keys: dict[str, set[str]] = {}

    def keys(self, table: str) -> set[str]:
        if table not in self._keys:
            self._keys[table] = {row.key for row in self.tables.get(table, []) if row.key}
        return self._keys[table]

    @cached_property
    def holidays(self) -> set[date]:
        """Tanggal D-11 holidays yang terbaca (baris berformat salah dicatat aturan 007)."""
        days = (
            parse_date(r.values.get("holiday_date"), ISO) for r in self.tables.get("holidays", [])
        )
        return {day for day in days if day}

    @cached_property
    def complexity_ranges(self) -> dict[str, tuple[float, float]]:
        """complexity_id -> (min_days, max_days) dari D-04 yang angkanya terbaca."""
        ranges = {}
        for row in self.tables.get("complexity_levels", []):
            try:
                ranges[row.key] = (float(row.values["min_days"]), float(row.values["max_days"]))
            except (KeyError, ValueError):
                continue
        return ranges


RULES: dict[str, Rule] = {}


def register(rule: Rule) -> Rule:
    if rule.rule_id in RULES:
        raise ValueError(f"rule_id ganda: {rule.rule_id}")
    RULES[rule.rule_id] = rule
    return rule


def run_rules(tables: Tables, source: str, rules: Iterable[Rule] | None = None) -> Report:
    """Jalankan setiap aturan berbasis baris yang tabelnya ada di `tables`."""
    report = Report(source)
    context = Context(tables)
    for rule in rules if rules is not None else RULES.values():
        if rule.check is None or rule.table not in tables:
            continue
        rows = tables[rule.table]
        hits = list(rule.check(rows, context))
        report.findings.extend(
            Finding(
                rule.rule_id,
                rule.characteristic,
                rule.level,
                source,
                rule.table,
                hit.row.number,
                hit.row.key,
                hit.column,
                hit.value,
                hit.message,
            )
            for hit in hits
        )
        report.summaries.append(
            RuleSummary(
                rule.rule_id,
                source,
                rule.table,
                rule.characteristic,
                rule.level,
                rule.text,
                checked=len(rows),
                violated=len({id(hit.row) for hit in hits}),
            )
        )
    return report
