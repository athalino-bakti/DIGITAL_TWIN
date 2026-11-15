"""Pemeriksaan skema basis data terhadap Data Dictionary di DATA_CONTRACT.md (DIG-195).

Dari folder backend, dengan basis data yang sudah di-`alembic upgrade head`:
    python -m app.qa.schema_check
    python -m app.qa.schema_check --database-url postgresql+psycopg://...
    python -m app.qa.schema_check --contract ../docs/DATA_CONTRACT.md

Yang dibandingkan untuk setiap tabel D-01 sampai D-11 di bagian 6 DATA_CONTRACT:
- tabel ada, dan daftar kolomnya sama persis (tidak ada yang hilang atau berlebih);
- tipe PostgreSQL, wajib (NOT NULL), dan nilai default tiap kolom;
- primary key dan foreign key (kolom serta tabel/kolom tujuannya);
- aturan di basis data: setiap nama `ck_`, `uq_`, dan `ex_` yang ditulis di dokumen ada di basis
  data, dan sebaliknya tidak ada aturan di basis data yang belum dicatat di dokumen.

Selain itu "Tipe DD" diperiksa cocok dengan "Tipe PostgreSQL" (misalnya integer harus INTEGER).
Keluar dengan kode 0 bila semuanya cocok, 1 bila ada selisih. Hanya membaca katalog basis data.
"""

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

DEFAULT_CONTRACT = Path(__file__).resolve().parents[3] / "docs" / "DATA_CONTRACT.md"
SCHEMA = "public"

# Tipe DD yang boleh dipakai untuk setiap tipe dasar PostgreSQL.
DD_TYPES = {
    "VARCHAR": {"string", "enum"},
    "TEXT": {"string"},
    "INTEGER": {"integer"},
    "DOUBLE PRECISION": {"float"},
    "DATE": {"date"},
    "BOOLEAN": {"boolean"},
}
# Nama aturan yang dibandingkan dua arah. pk_ dan fk_ diperiksa lewat kolom PK/FK.
RULE_PREFIXES = ("ck_", "uq_", "ex_")

_HEADING = re.compile(r"^### (D-\d{2}) `(\w+)`")
_RULE = re.compile(r"^- `((?:ck|uq|ex)_\w+)`")
_COLUMN = re.compile(r"^`(\w+)`(?: \((PK|FK ke `(\w+)\.(\w+)`)\))?$")


@dataclass
class Column:
    name: str
    dd_type: str
    pg_type: str
    required: bool
    default: str | None = None
    primary_key: bool = False
    references: tuple[str, str] | None = None


@dataclass
class TableSpec:
    code: str
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    rules: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class Problem:
    table: str
    message: str

    def __str__(self) -> str:
        return f"{self.table}: {self.message}"


# --- membaca dokumen ------------------------------------------------------------------


def parse_contract(markdown: str) -> dict[str, TableSpec]:
    """Tabel D-01 sampai D-11 dari bagian 6 DATA_CONTRACT.md.

    Aturan hanya diambil dari daftar di bawah "Aturan di basis data:". Aturan validator
    aplikasi (misalnya hotfix D-08) ditulis di paragraf lain dan sengaja tidak ikut.
    """
    tables: dict[str, TableSpec] = {}
    current: TableSpec | None = None
    in_section = in_rules = False
    for raw in markdown.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line.startswith("## 6.")
            current = None
            continue
        if not in_section:
            continue
        heading = _HEADING.match(line)
        if heading:
            current = TableSpec(code=heading.group(1), name=heading.group(2))
            tables[current.name] = current
            in_rules = False
            continue
        if current is None or not line:
            continue
        if line.startswith("Aturan di basis data"):
            in_rules = True
            continue
        if line.startswith("|"):
            column = _parse_column_row(line)
            if column is not None:
                current.columns[column.name] = column
            continue
        if line.startswith("- ") and in_rules:
            rule = _RULE.match(line)
            if rule:
                current.rules.add(rule.group(1))
            continue
        in_rules = False  # paragraf lain menutup daftar aturan
    return tables


def _parse_column_row(line: str) -> Column | None:
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) < 4:
        return None
    match = _COLUMN.match(cells[0])
    if match is None:  # baris judul atau pemisah tabel
        return None
    name, key, ref_table, ref_column = match.groups()
    pg_type, _, default = cells[2].partition(", default ")
    return Column(
        name=name,
        dd_type=cells[1],
        pg_type=pg_type.strip().upper(),
        required=cells[3] == "Ya",
        default=default.strip() or None,
        primary_key=key == "PK",
        references=(ref_table, ref_column) if ref_table else None,
    )


# --- membaca basis data ---------------------------------------------------------------


@dataclass
class DbTable:
    columns: dict[str, dict] = field(default_factory=dict)
    primary_key: set[str] = field(default_factory=set)
    foreign_keys: dict[str, tuple[str, str]] = field(default_factory=dict)
    rules: set[str] = field(default_factory=set)


def read_database(connection: Connection, tables: Iterable[str]) -> dict[str, DbTable]:
    names = sorted(tables)
    result = {name: DbTable() for name in names}
    params = {"schema": SCHEMA, "tables": names}

    columns = connection.execute(
        text(
            "SELECT table_name, column_name, data_type, character_maximum_length,"
            " is_nullable, column_default"
            " FROM information_schema.columns"
            " WHERE table_schema = :schema AND table_name = ANY(:tables)"
        ),
        params,
    )
    for table, column, data_type, length, nullable, default in columns:
        result[table].columns[column] = {
            "type": _pg_type(data_type, length),
            "required": nullable == "NO",
            "default": default,
        }

    keys = connection.execute(
        text(
            "SELECT tc.table_name, tc.constraint_type, kcu.column_name,"
            " ccu.table_name, ccu.column_name"
            " FROM information_schema.table_constraints tc"
            " JOIN information_schema.key_column_usage kcu"
            "   ON kcu.constraint_schema = tc.constraint_schema"
            "  AND kcu.constraint_name = tc.constraint_name"
            " JOIN information_schema.constraint_column_usage ccu"
            "   ON ccu.constraint_schema = tc.constraint_schema"
            "  AND ccu.constraint_name = tc.constraint_name"
            " WHERE tc.table_schema = :schema AND tc.table_name = ANY(:tables)"
            "   AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')"
        ),
        params,
    )
    for table, kind, column, ref_table, ref_column in keys:
        if kind == "PRIMARY KEY":
            result[table].primary_key.add(column)
        else:
            result[table].foreign_keys[column] = (ref_table, ref_column)

    constraints = connection.execute(
        text(
            "SELECT c.relname, con.conname"
            " FROM pg_constraint con"
            " JOIN pg_class c ON c.oid = con.conrelid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = :schema AND c.relname = ANY(:tables)"
            " UNION"
            " SELECT tablename, indexname FROM pg_indexes"
            " WHERE schemaname = :schema AND tablename = ANY(:tables)"
        ),
        params,
    )
    for table, name in constraints:
        if name.startswith(RULE_PREFIXES):
            result[table].rules.add(name)

    existing = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = :schema AND table_name = ANY(:tables)"
        ),
        params,
    )
    found = {row[0] for row in existing}
    return {name: table for name, table in result.items() if name in found}


def _pg_type(data_type: str, length: int | None) -> str:
    if data_type == "character varying":
        return f"VARCHAR({length})" if length else "VARCHAR"
    return data_type.upper()


def _normalize_default(value: str | None) -> str | None:
    """Samakan bentuk default dokumen dan basis data.

    `'not_started'::character varying` menjadi `not_started`, `'3'::double precision` menjadi 3.0.
    """
    if value is None:
        return None
    value = value.split("::", 1)[0].strip().strip("'")
    try:
        return repr(float(value))
    except ValueError:
        return value.lower()


# --- membandingkan --------------------------------------------------------------------


def check_contract_types(specs: dict[str, TableSpec]) -> list[Problem]:
    """Tipe DD dan Tipe PostgreSQL di dokumen harus sejalan."""
    problems = []
    for spec in specs.values():
        for column in spec.columns.values():
            base = column.pg_type.split("(", 1)[0]
            allowed = DD_TYPES.get(base)
            if allowed is None:
                problems.append(
                    Problem(
                        spec.name, f"{column.name}: tipe PostgreSQL {column.pg_type} tidak dikenal"
                    )
                )
            elif column.dd_type not in allowed:
                problems.append(
                    Problem(
                        spec.name,
                        f"{column.name}: tipe DD {column.dd_type} "
                        f"tidak cocok dengan {column.pg_type}",
                    )
                )
    return problems


def compare(specs: dict[str, TableSpec], database: dict[str, DbTable]) -> list[Problem]:
    problems: list[Problem] = []
    for name, spec in specs.items():
        table = database.get(name)
        if table is None:
            problems.append(Problem(name, "tabel tidak ada di basis data"))
            continue

        for column in sorted(set(spec.columns) - set(table.columns)):
            problems.append(
                Problem(name, f"kolom {column} ada di dokumen, tidak ada di basis data")
            )
        for column in sorted(set(table.columns) - set(spec.columns)):
            problems.append(
                Problem(name, f"kolom {column} ada di basis data, tidak ada di dokumen")
            )

        for column_name, column in spec.columns.items():
            actual = table.columns.get(column_name)
            if actual is None:
                continue
            if actual["type"] != column.pg_type:
                problems.append(
                    Problem(
                        name,
                        f"{column_name}: tipe dokumen {column.pg_type}, "
                        f"basis data {actual['type']}",
                    )
                )
            if actual["required"] != column.required:
                expected = "wajib" if column.required else "boleh kosong"
                problems.append(
                    Problem(name, f"{column_name}: dokumen {expected}, basis data berbeda")
                )
            documented = _normalize_default(column.default)
            stored = _normalize_default(actual["default"])
            if documented != stored:
                problems.append(
                    Problem(
                        name,
                        f"{column_name}: default dokumen {column.default or '(tidak ada)'}, "
                        f"basis data {actual['default'] or '(tidak ada)'}",
                    )
                )

        documented_pk = {c.name for c in spec.columns.values() if c.primary_key}
        if documented_pk != table.primary_key:
            problems.append(
                Problem(
                    name,
                    f"primary key dokumen {sorted(documented_pk)}, "
                    f"basis data {sorted(table.primary_key)}",
                )
            )

        documented_fk = {c.name: c.references for c in spec.columns.values() if c.references}
        for column in sorted(set(documented_fk) | set(table.foreign_keys)):
            expected = documented_fk.get(column)
            actual_ref = table.foreign_keys.get(column)
            if expected != actual_ref:
                problems.append(
                    Problem(
                        name,
                        f"{column}: foreign key dokumen {_ref(expected)}, "
                        f"basis data {_ref(actual_ref)}",
                    )
                )

        for rule in sorted(spec.rules - table.rules):
            problems.append(Problem(name, f"aturan {rule} ada di dokumen, tidak ada di basis data"))
        for rule in sorted(table.rules - spec.rules):
            problems.append(Problem(name, f"aturan {rule} ada di basis data, tidak ada di dokumen"))
    return problems


def _ref(reference: tuple[str, str] | None) -> str:
    return f"{reference[0]}.{reference[1]}" if reference else "(tidak ada)"


def run_check(connection: Connection, contract: str) -> tuple[dict[str, TableSpec], list[Problem]]:
    specs = parse_contract(contract)
    if not specs:
        return specs, [Problem("DATA_CONTRACT", "bagian 6 tidak ditemukan atau kosong")]
    problems = check_contract_types(specs)
    problems += compare(specs, read_database(connection, specs))
    return specs, problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bandingkan skema basis data dengan DATA_CONTRACT")
    parser.add_argument("--database-url", help="Bawaan: DATABASE_URL dari .env")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    args = parser.parse_args(argv)

    if args.database_url:
        url = args.database_url
    else:
        from app.core.config import get_settings

        url = get_settings().database_url
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            specs, problems = run_check(connection, args.contract.read_text(encoding="utf-8"))
    finally:
        engine.dispose()

    columns = sum(len(spec.columns) for spec in specs.values())
    rules = sum(len(spec.rules) for spec in specs.values())
    if problems:
        print(f"Ditemukan {len(problems)} selisih antara basis data dan DATA_CONTRACT:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(f"Cocok: {len(specs)} tabel, {columns} kolom, dan {rules} aturan sesuai DATA_CONTRACT.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
