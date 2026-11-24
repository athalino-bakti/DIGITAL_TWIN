"""Pemeriksaan skema basis data terhadap Data Dictionary di DATA_CONTRACT.md (DIG-195).

Dari folder backend, dengan basis data yang sudah di-`alembic upgrade head`:
    python -m app.qa.schema_check
    python -m app.qa.schema_check --database-url postgresql+psycopg://...
    python -m app.qa.schema_check --contract ../docs/DATA_CONTRACT.md

Yang dibandingkan untuk setiap tabel D-01 sampai D-11 di bagian 6 DATA_CONTRACT:
- tabel ada, dan daftar kolomnya sama persis (tidak ada yang hilang atau berlebih);
- tipe PostgreSQL, wajib (NOT NULL), dan nilai default tiap kolom;
- primary key dan foreign key (kolom serta tabel/kolom tujuannya), termasuk aksi ON DELETE.
  Dokumen menulis FK sebagai `(FK ke `tabel.kolom`)`, yang berarti ON DELETE NO ACTION (baris
  induk tidak bisa dihapus selama masih dirujuk). Aksi lain ditulis
  `(FK ke `tabel.kolom`, ON DELETE CASCADE)`;
- aturan di basis data: setiap nama `ck_`, `uq_`, dan `ex_` yang ditulis di dokumen ada di basis
  data, dan sebaliknya tidak ada aturan di basis data yang belum dicatat di dokumen;
- isi aturan `ck_` (DIG-228): ekspresi setelah nama aturan di dokumen dibandingkan dengan
  CHECK di basis data. Karena PostgreSQL menulis ulang ekspresi (menambah kurung dan cast,
  `IN (...)` menjadi `= ANY (ARRAY[...])`), ekspresi dokumen lebih dulu dipasang ke tabel
  sementara dengan kolom yang sama, lalu kedua bentuk dibandingkan setelah sama-sama ditulis
  ulang PostgreSQL. Isi `uq_` dan `ex_` ditulis sebagai kalimat, jadi hanya namanya yang dicek.

Selain itu "Tipe DD" diperiksa cocok dengan "Tipe PostgreSQL" (misalnya integer harus INTEGER).
Tabel markdown boleh ditulis tanpa pipa di tepi, dan kolom Wajib tidak peka huruf besar-kecil.

Keluar dengan kode 0 bila semuanya cocok, 1 bila ada selisih. Basis data tidak diubah: tabel
sementara untuk membandingkan CHECK dibuat di dalam savepoint yang selalu di-rollback.
"""

import argparse
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

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
_RULE = re.compile(r"^- `((?:ck|uq|ex)_\w+)`(?::\s*`([^`]+)`\s*$)?")
_ON_DELETE = r"(CASCADE|SET NULL|SET DEFAULT|RESTRICT|NO ACTION)"
_COLUMN = re.compile(
    r"^`(\w+)`(?: \((PK|FK ke `(\w+)\.(\w+)`(?:, ON DELETE " + _ON_DELETE + r")?)\))?$"
)
_QUOTED = re.compile(r"'(?:[^']|'')*'")
# confdeltype di pg_constraint.
ON_DELETE_CODES = {
    "a": "NO ACTION",
    "r": "RESTRICT",
    "c": "CASCADE",
    "n": "SET NULL",
    "d": "SET DEFAULT",
}


@dataclass
class Column:
    name: str
    dd_type: str
    pg_type: str
    required: bool
    default: str | None = None
    primary_key: bool = False
    references: tuple[str, str] | None = None
    on_delete: str = "NO ACTION"


@dataclass
class TableSpec:
    code: str
    name: str
    columns: dict[str, Column] = field(default_factory=dict)
    rules: set[str] = field(default_factory=set)
    # Ekspresi aturan ck_ seperti ditulis di dokumen.
    checks: dict[str, str] = field(default_factory=dict)


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
    aplikasi yang ditulis di luar daftar itu sengaja tidak ikut, karena tidak ada di basis data.
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
        if line.startswith("- "):
            rule = _RULE.match(line) if in_rules else None
            if rule:
                name, expression = rule.groups()
                current.rules.add(name)
                if expression and name.startswith("ck_"):
                    current.checks[name] = expression
            continue
        if "|" in line:  # mungkin baris tabel, dengan atau tanpa pipa di tepi
            column = _parse_column_row(line)
            if column is not None:
                current.columns[column.name] = column
                continue
            if _is_table_line(line):  # baris judul atau pemisah tabel
                continue
        in_rules = False  # paragraf lain (termasuk yang memuat |) menutup daftar aturan
    return tables


def _is_table_line(line: str) -> bool:
    """Baris judul atau pemisah tabel markdown, dengan atau tanpa pipa di tepi."""
    stripped = line.strip()
    if stripped.startswith("|"):
        return True
    first = stripped.split("|", 1)[0].strip()
    return set(stripped) <= set("|-: ") or first == "Kolom"


def _parse_column_row(line: str) -> Column | None:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    if len(cells) < 4:
        return None
    match = _COLUMN.match(cells[0])
    if match is None:  # baris judul atau pemisah tabel
        return None
    name, key, ref_table, ref_column, on_delete = match.groups()
    pg_type, _, default = cells[2].partition(", default ")
    return Column(
        name=name,
        dd_type=cells[1],
        pg_type=pg_type.strip().upper(),
        required=cells[3].strip("*").strip().lower() == "ya",
        default=default.strip() or None,
        primary_key=key == "PK",
        references=(ref_table, ref_column) if ref_table else None,
        on_delete=on_delete or "NO ACTION",
    )


# --- membaca basis data ---------------------------------------------------------------


@dataclass
class DbTable:
    columns: dict[str, dict] = field(default_factory=dict)
    primary_key: set[str] = field(default_factory=set)
    foreign_keys: dict[str, tuple[str, str]] = field(default_factory=dict)
    on_delete: dict[str, str] = field(default_factory=dict)
    rules: set[str] = field(default_factory=set)
    # Definisi CHECK dari pg_get_constraintdef, per nama constraint.
    checks: dict[str, str] = field(default_factory=dict)


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

    definitions = connection.execute(
        text(
            "SELECT c.relname, con.conname, con.contype, con.confdeltype,"
            " pg_get_constraintdef(con.oid), a.attname"
            " FROM pg_constraint con"
            " JOIN pg_class c ON c.oid = con.conrelid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            # Hanya kolom pertama FK yang dibaca: FK multi-kolom belum didukung (D-01 sampai
            # D-11 tidak punya). Bila nanti ada, aksi ON DELETE-nya hanya tercatat di kolom
            # pertama.
            " LEFT JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = con.conkey[1]"
            " WHERE n.nspname = :schema AND c.relname = ANY(:tables)"
            "   AND con.contype IN ('c', 'f')"
        ),
        params,
    )
    for table, name, kind, delete_code, definition, column in definitions:
        if kind == "c":
            result[table].checks[name] = definition
        elif column is not None:
            result[table].on_delete[column] = ON_DELETE_CODES.get(delete_code, delete_code)

    existing = connection.execute(
        text(
            "SELECT table_name FROM information_schema.tables"
            " WHERE table_schema = :schema AND table_name = ANY(:tables)"
        ),
        params,
    )
    found = {row[0] for row in existing}
    return {name: table for name, table in result.items() if name in found}


def render_check(connection: Connection, table: str, expression: str) -> str:
    """Bentuk CHECK dari ekspresi dokumen setelah ditulis ulang PostgreSQL.

    Ekspresi dipasang ke tabel sementara berkolom sama (`LIKE`), dibaca dengan
    `pg_get_constraintdef`, lalu savepoint di-rollback sehingga tidak ada yang tersimpan.
    Melempar ValueError bila ekspresi tidak bisa dibaca PostgreSQL.
    """
    # Titik koma di luar literal string bisa menyelipkan perintah SQL kedua.
    if ";" in _QUOTED.sub("''", expression):
        raise ValueError("ekspresi tidak boleh berisi titik koma di luar teks berkutip")
    savepoint = connection.begin_nested()
    try:
        connection.exec_driver_sql(f'CREATE TEMP TABLE "_cek_skema" (LIKE "{SCHEMA}"."{table}")')
        connection.exec_driver_sql(
            f'ALTER TABLE "_cek_skema" ADD CONSTRAINT "_cek" CHECK ({expression}) NOT VALID'
        )
        definition = connection.exec_driver_sql(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
            " WHERE conname = '_cek' AND conrelid = '_cek_skema'::regclass"
        ).scalar_one()
    except DBAPIError as exc:
        raise ValueError(str(exc.orig).splitlines()[0]) from exc
    finally:
        savepoint.rollback()
    return definition.removesuffix(" NOT VALID")


def compare_checks(
    connection: Connection, specs: dict[str, TableSpec], database: dict[str, DbTable]
) -> list[Problem]:
    """Isi aturan ck_ di dokumen dibandingkan dengan CHECK di basis data (DIG-228)."""
    problems = []
    for name, spec in specs.items():
        table = database.get(name)
        if table is None:
            continue
        for rule, expression in sorted(spec.checks.items()):
            stored = table.checks.get(rule)
            if stored is None:  # selisih nama sudah dilaporkan compare()
                continue
            try:
                documented = render_check(connection, name, expression)
            except ValueError as exc:
                problems.append(Problem(name, f"aturan {rule}: ekspresi dokumen tidak sah ({exc})"))
                continue
            if documented != stored:
                problems.append(
                    Problem(
                        name,
                        f"aturan {rule}: isi dokumen {documented}, basis data {stored}",
                    )
                )
    return problems


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
            elif expected is not None:
                documented_action = spec.columns[column].on_delete
                stored_action = table.on_delete.get(column, "NO ACTION")
                if documented_action != stored_action:
                    problems.append(
                        Problem(
                            name,
                            f"{column}: ON DELETE dokumen {documented_action}, "
                            f"basis data {stored_action}",
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
    database = read_database(connection, specs)
    problems += compare(specs, database)
    problems += compare_checks(connection, specs, database)
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
    checks = sum(len(spec.checks) for spec in specs.values())
    if problems:
        print(f"Ditemukan {len(problems)} selisih antara basis data dan DATA_CONTRACT:")
        for problem in problems:
            print(f"- {problem}")
        return 1
    print(
        f"Cocok: {len(specs)} tabel, {columns} kolom, dan {rules} aturan sesuai DATA_CONTRACT"
        f" (isi {checks} aturan CHECK ikut dibandingkan)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
