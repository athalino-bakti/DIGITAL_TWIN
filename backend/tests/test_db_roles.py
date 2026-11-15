"""DIG-223: hak akses role jc_app dan schema twinner terhadap PostgreSQL sungguhan.

Ikut grup tes migrasi (`-m migration`) karena membutuhkan MIGRATION_TEST_DATABASE_URL
dengan nama berakhiran `_test` dan user yang boleh membuat role (superuser/CREATEROLE).
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy.exc import ProgrammingError

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.getenv("MIGRATION_TEST_DATABASE_URL")
DML = ("SELECT", "INSERT", "UPDATE", "DELETE")

pytestmark = [
    pytest.mark.migration,
    pytest.mark.skipif(not TEST_DB_URL, reason="MIGRATION_TEST_DATABASE_URL belum diisi"),
]


def alembic(connection: Connection, action, target: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["connection"] = connection
    action(config, target)


@pytest.fixture(scope="module")
def engine() -> Engine:
    url = make_url(TEST_DB_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail(f"Nama database tes harus berakhiran '_test' (sekarang: {url.database!r})")
    test_engine = create_engine(url)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def migrated(engine: Engine) -> Engine:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS twinner CASCADE"))
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        alembic(connection, command.upgrade, "head")
    return engine


def as_jc_app(engine: Engine, sql: str, params: dict | None = None) -> None:
    """Jalankan satu perintah sebagai jc_app lalu batalkan (rollback)."""
    with engine.connect() as connection:
        with connection.begin() as transaction:
            connection.execute(text("SET LOCAL ROLE jc_app"))
            connection.execute(text(sql), params or {})
            transaction.rollback()


def scalar(engine: Engine, sql: str, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar()


def public_tables(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


# --- role dan schema --------------------------------------------------------------


def test_jc_app_role_exists_without_login(migrated):
    # Role berlaku untuk seluruh server, jadi bisa tersisa dari run lain. Hapus dulu agar
    # yang diuji benar-benar role buatan migrasi ini.
    with migrated.begin() as connection:
        alembic(connection, command.downgrade, "0006")
    try:
        with migrated.begin() as connection:
            connection.execute(text("DROP ROLE IF EXISTS jc_app"))
    except Exception:
        pytest.skip("jc_app masih punya hak di basis data lain pada server ini")
    finally:
        with migrated.begin() as connection:
            alembic(connection, command.upgrade, "head")

    row = scalar(migrated, "SELECT rolcanlogin FROM pg_roles WHERE rolname = 'jc_app'")
    assert row is False, "jc_app harus NOLOGIN; login dan password diberi admin di luar repo"
    assert (
        scalar(
            migrated,
            "SELECT rolsuper OR rolcreaterole OR rolcreatedb FROM pg_roles "
            "WHERE rolname = 'jc_app'",
        )
        is False
    )


def test_twinner_schema_exists_and_is_closed_to_jc_app(migrated):
    assert scalar(migrated, "SELECT 1 FROM pg_namespace WHERE nspname = 'twinner'") == 1
    for privilege in ("USAGE", "CREATE"):
        has = scalar(migrated, "SELECT has_schema_privilege('jc_app', 'twinner', :p)", p=privilege)
        assert has is False, f"jc_app tidak boleh punya {privilege} di schema twinner"


# --- baca-tulis data di public -------------------------------------------------------


def test_jc_app_has_dml_on_every_final_source_table(migrated):
    tables = [t for t in public_tables(migrated) if t != "alembic_version"]
    assert "projects" in tables and "holidays" in tables

    missing = [
        f"{table}.{privilege}"
        for table in tables
        for privilege in DML
        if not scalar(
            migrated,
            "SELECT has_table_privilege('jc_app', :t, :p)",
            t=f"public.{table}",
            p=privilege,
        )
    ]
    assert missing == []


def test_jc_app_can_actually_read_and_write_rows(migrated):
    as_jc_app(
        migrated,
        "INSERT INTO holidays (holiday_date, holiday_name) VALUES ('2026-12-25', 'Natal');"
        "UPDATE holidays SET holiday_name = 'Hari Natal' WHERE holiday_date = '2026-12-25';"
        "SELECT count(*) FROM projects;"
        "DELETE FROM holidays WHERE holiday_date = '2026-12-25'",
    )


def test_jc_app_cannot_truncate(migrated):
    assert (
        scalar(migrated, "SELECT has_table_privilege('jc_app', 'public.holidays', 'TRUNCATE')")
        is False
    )


# --- tidak boleh mengubah struktur --------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE public.tabel_liar (id int)",
        "DROP TABLE public.holidays",
        "ALTER TABLE public.holidays ADD COLUMN catatan text",
        "CREATE TABLE twinner.scenario (id int)",
        "SELECT 1 FROM twinner.pg_class_does_not_matter",
    ],
)
def test_jc_app_cannot_change_structure_or_touch_twinner(migrated, sql):
    with pytest.raises(ProgrammingError, match="permission denied|must be owner"):
        as_jc_app(migrated, sql)


def test_jc_app_can_read_but_not_change_migration_history(migrated):
    as_jc_app(migrated, "SELECT version_num FROM alembic_version")
    with pytest.raises(ProgrammingError, match="permission denied"):
        as_jc_app(migrated, "UPDATE alembic_version SET version_num = 'palsu'")


# --- tabel dari migrasi berikutnya -----------------------------------------------------------


def test_existing_role_is_left_untouched(migrated):
    """Login yang sudah diaktifkan admin di staging tidak boleh tertimpa migrasi."""
    with migrated.begin() as connection:
        alembic(connection, command.downgrade, "0006")
        connection.execute(text("ALTER ROLE jc_app LOGIN"))
    try:
        with migrated.begin() as connection:
            alembic(connection, command.upgrade, "head")
        assert scalar(migrated, "SELECT rolcanlogin FROM pg_roles WHERE rolname = 'jc_app'")
    finally:
        with migrated.begin() as connection:
            connection.execute(text("ALTER ROLE jc_app NOLOGIN"))


def test_tables_from_later_migrations_are_granted_automatically(migrated):
    with migrated.begin() as connection:
        # Meniru migrasi baru yang dijalankan role pemilik yang sama.
        connection.execute(
            text("CREATE TABLE public.uji_migrasi_baru (id serial PRIMARY KEY, x int)")
        )
    try:
        as_jc_app(migrated, "INSERT INTO uji_migrasi_baru (x) VALUES (1)")
    finally:
        with migrated.begin() as connection:
            connection.execute(text("DROP TABLE public.uji_migrasi_baru"))


# --- downgrade ----------------------------------------------------------------------------


def test_downgrade_removes_schema_and_privileges(migrated):
    with migrated.begin() as connection:
        alembic(connection, command.downgrade, "0006")

    assert scalar(migrated, "SELECT 1 FROM pg_namespace WHERE nspname = 'twinner'") is None
    assert (
        scalar(migrated, "SELECT has_table_privilege('jc_app', 'public.holidays', 'SELECT')")
        is False
    )

    with migrated.begin() as connection:
        alembic(connection, command.upgrade, "head")


def test_downgrade_refuses_to_drop_twinner_data(migrated):
    with migrated.begin() as connection:
        connection.execute(text("CREATE TABLE twinner.scenario (id int)"))

    try:
        with pytest.raises(Exception, match="depend"):
            with migrated.begin() as connection:
                alembic(connection, command.downgrade, "0006")
        assert scalar(migrated, "SELECT to_regclass('twinner.scenario') IS NOT NULL") is True
    finally:
        with migrated.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS twinner.scenario"))
