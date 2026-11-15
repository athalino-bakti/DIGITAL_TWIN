"""DIG-195: pemeriksaan skema basis data terhadap Data Dictionary di DATA_CONTRACT.md."""

import pytest
from sqlalchemy import text

from app.qa import schema_check
from app.qa.schema_check import (
    DEFAULT_CONTRACT,
    check_contract_types,
    parse_contract,
    run_check,
)
from tests.conftest import REQUIRES_DB, TEST_DB_URL

CONTRACT = DEFAULT_CONTRACT.read_text(encoding="utf-8")


def requires_db(test):
    for mark in REQUIRES_DB:
        test = mark(test)
    return test


DD_TABLES = [
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
]


# --- membaca dokumen (tanpa basis data) ------------------------------------------------


def test_contract_has_all_eleven_data_dictionary_tables():
    specs = parse_contract(CONTRACT)
    assert list(specs) == DD_TABLES
    assert [spec.code for spec in specs.values()] == [f"D-{n:02d}" for n in range(1, 12)]


def test_columns_keys_and_defaults_are_read_from_the_table():
    specs = parse_contract(CONTRACT)

    projects = specs["projects"]
    assert len(projects.columns) == 9
    assert projects.columns["project_id"].primary_key
    assert projects.columns["project_id"].pg_type == "VARCHAR(20)"
    assert projects.columns["actual_launch_date"].required is False
    assert projects.columns["dor_fulfilled"].default == "false"

    assert specs["resources"].columns["primary_role_id"].references == ("roles", "role_id")
    assert specs["tasks"].columns["status"].default == "not_started"
    assert specs["roles"].columns["capacity_reference"].pg_type == "DOUBLE PRECISION"


def test_only_database_rules_are_collected():
    specs = parse_contract(CONTRACT)
    assert all(rule.startswith(("ck_", "uq_", "ex_")) for rule in specs["workload_items"].rules)
    assert len(specs["workload_items"].rules) == 6
    assert "ex_availability_no_overlap" in specs["availability"].rules
    assert "uq_projects_active_priority" in specs["projects"].rules
    assert specs["holidays"].rules == set()


def test_validator_rules_outside_the_database_list_are_ignored():
    markdown = """
## 6. Salinan Data Dictionary

### D-01 `projects`

| Kolom | Tipe DD | Tipe PostgreSQL | Wajib | Keterangan |
|---|---|---|---|---|
| `project_id` (PK) | string | VARCHAR(20) | Ya | Format PRJ-001 |

Aturan di basis data:

- `ck_projects_project_id_format`: `project_id ~ '^PRJ-[0-9]{3,}$'`

Aturan validator J&C (bukan di basis data):

- `ck_projects_validator_saja`: dicek di service
"""
    assert parse_contract(markdown)["projects"].rules == {"ck_projects_project_id_format"}


def test_tables_outside_section_six_are_ignored():
    specs = parse_contract(CONTRACT)
    assert "staging_trello_action" not in specs and "app_user" not in specs


def test_document_types_are_consistent():
    assert check_contract_types(parse_contract(CONTRACT)) == []


def test_mismatched_dd_type_is_reported():
    broken = CONTRACT.replace(
        "| `priority_rank` | integer | INTEGER | Ya | Angka 1 adalah prioritas tertinggi antar",
        "| `priority_rank` | float | INTEGER | Ya | Angka 1 adalah prioritas tertinggi antar",
    )
    assert broken != CONTRACT
    problems = check_contract_types(parse_contract(broken))
    assert [str(p) for p in problems] == [
        "projects: priority_rank: tipe DD float tidak cocok dengan INTEGER"
    ]


@pytest.mark.parametrize(
    ("documented", "stored"),
    [
        ("false", "false"),
        ("3.0", "'3'::double precision"),
        ("not_started", "'not_started'::character varying"),
        ("0", "0"),
    ],
)
def test_defaults_are_compared_after_normalizing(documented, stored):
    normalize = schema_check._normalize_default
    assert normalize(documented) == normalize(stored)


# --- terhadap basis data hasil migrasi -------------------------------------------------


@pytest.fixture
def connection(session_factory):
    """Koneksi dalam transaksi yang selalu di-rollback, jadi ALTER TABLE di tes tidak tersimpan."""
    engine = session_factory.kw["bind"]
    with engine.connect() as conn:
        transaction = conn.begin()
        yield conn
        transaction.rollback()


def problems_of(connection, contract: str = CONTRACT) -> list[str]:
    return [str(problem) for problem in run_check(connection, contract)[1]]


@requires_db
def test_migrated_database_matches_contract(connection):
    """Penjaga: setiap migrasi yang mengubah tabel D-01 sampai D-11 wajib ikut memperbarui
    DATA_CONTRACT bagian 6, dan sebaliknya."""
    assert problems_of(connection) == []


DB_CHANGES = [
    (
        "ALTER TABLE projects ADD COLUMN catatan TEXT",
        "projects: kolom catatan ada di basis data, tidak ada di dokumen",
    ),
    (
        "ALTER TABLE holidays DROP COLUMN holiday_name",
        "holidays: kolom holiday_name ada di dokumen, tidak ada di basis data",
    ),
    (
        "ALTER TABLE roles ALTER COLUMN role_name TYPE VARCHAR(150)",
        "roles: role_name: tipe dokumen VARCHAR(100), basis data VARCHAR(150)",
    ),
    (
        "ALTER TABLE resources ALTER COLUMN seniority DROP NOT NULL",
        "resources: seniority: dokumen wajib, basis data berbeda",
    ),
    (
        "ALTER TABLE tasks ALTER COLUMN status DROP DEFAULT",
        "tasks: status: default dokumen not_started, basis data (tidak ada)",
    ),
    (
        "ALTER TABLE projects DROP CONSTRAINT ck_projects_status_valid",
        "projects: aturan ck_projects_status_valid ada di dokumen, tidak ada di basis data",
    ),
    (
        "ALTER TABLE holidays ADD CONSTRAINT ck_holidays_name_not_blank CHECK (holiday_name <> '')",
        "holidays: aturan ck_holidays_name_not_blank ada di basis data, tidak ada di dokumen",
    ),
    (
        "DROP INDEX uq_projects_active_priority",
        "projects: aturan uq_projects_active_priority ada di dokumen, tidak ada di basis data",
    ),
    (
        "ALTER TABLE assignments DROP CONSTRAINT fk_assignments_resource_id_resources",
        "assignments: resource_id: foreign key dokumen resources.resource_id, "
        "basis data (tidak ada)",
    ),
]


@requires_db
@pytest.mark.parametrize(("statement", "expected"), DB_CHANGES)
def test_database_change_without_contract_update_is_reported(connection, statement, expected):
    connection.execute(text(statement))
    assert problems_of(connection) == [expected]


DOC_CHANGES = [
    (
        "| `holiday_name` | string | VARCHAR(200) | Ya | Nama libur nasional atau cuti bersama |\n",
        "",
        "holidays: kolom holiday_name ada di basis data, tidak ada di dokumen",
    ),
    (
        "- `ck_roles_role_id_format`: `role_id ~ '^ROLE-[A-Z]+$'`\n",
        "",
        "roles: aturan ck_roles_role_id_format ada di basis data, tidak ada di dokumen",
    ),
    (
        "| `is_hotfix` | boolean | BOOLEAN, default false | Ya |",
        "| `is_hotfix` | boolean | BOOLEAN, default true | Ya |",
        "workload_items: is_hotfix: default dokumen true, basis data false",
    ),
]


@requires_db
@pytest.mark.parametrize(("old", "new", "expected"), DOC_CHANGES)
def test_contract_change_without_migration_is_reported(connection, old, new, expected):
    assert old in CONTRACT
    assert problems_of(connection, CONTRACT.replace(old, new, 1)) == [expected]


@requires_db
def test_cli_reports_match_and_mismatch(session_factory, tmp_path, capsys):
    assert schema_check.main(["--database-url", TEST_DB_URL]) == 0
    assert "Cocok: 11 tabel, 79 kolom" in capsys.readouterr().out

    contract = tmp_path / "DATA_CONTRACT.md"
    contract.write_text(CONTRACT.replace("### D-11 `holidays`", "### D-11 `hari_libur`"), "utf-8")
    assert schema_check.main(["--database-url", TEST_DB_URL, "--contract", str(contract)]) == 1
    assert "hari_libur: tabel tidak ada di basis data" in capsys.readouterr().out
