"""DIG-210 (story DIG-50): pool koneksi, batas waktu query, dan indeks foreign key."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db.session import engine_options
from tests.conftest import REQUIRES_DB, TEST_DB_URL

# Foreign key yang sengaja tanpa indeks. Kolomnya tidak dipakai untuk filter atau join;
# PostgreSQL hanya memeriksanya saat baris induk dihapus, yang jarang terjadi (akun pengguna,
# peran aplikasi, job impor, anggota). Indeks di sini hanya menambah beban tulis.
# Alasan per baris ada di docs/DATABASE.md. FK baru tanpa indeks wajib diputuskan di sini.
UNINDEXED_FK_ALLOWED = {
    ("audit_log", "actor_user_id"),
    ("event_log", "resource_id"),
    ("resource_alias", "mapped_by_user_id"),
    ("role_permission", "permission_code"),
    ("staging_trello_action", "import_job_id"),
    ("task_manual_change", "changed_by"),
    ("user_app_role", "role_code"),
}


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_default_pool_is_small_and_has_no_query_limit():
    options = engine_options(settings())
    assert (options["pool_size"], options["max_overflow"]) == (5, 5)
    assert options["pool_timeout"] == 10
    assert options["pool_recycle"] == 1800
    assert options["pool_pre_ping"] is True
    assert options["connect_args"] == {"connect_timeout": 3, "application_name": "jc-api"}


def test_timeouts_become_server_options():
    options = engine_options(
        settings(db_statement_timeout_ms=30000, db_idle_in_transaction_timeout_ms=300000)
    )
    assert options["connect_args"]["options"] == (
        "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=300000"
    )


def test_only_the_statement_timeout_can_be_set():
    options = engine_options(settings(db_statement_timeout_ms=500))
    assert options["connect_args"]["options"] == "-c statement_timeout=500"


@pytest.mark.parametrize(
    "values", [{"db_pool_size": 0}, {"db_max_overflow": -1}, {"db_statement_timeout_ms": -5}]
)
def test_invalid_pool_settings_are_rejected(values):
    with pytest.raises(ValueError):
        settings(**values)


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_statement_timeout_and_application_name_reach_postgresql(session_factory):
    engine = create_engine(
        TEST_DB_URL, **engine_options(settings(db_statement_timeout_ms=200, db_pool_size=1))
    )
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SHOW application_name")) == "jc-api"
            assert connection.scalar(text("SHOW statement_timeout")) == "200ms"
            with pytest.raises(OperationalError, match="statement timeout"):
                connection.execute(text("SELECT pg_sleep(1)"))
    finally:
        engine.dispose()


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_every_foreign_key_has_an_index_or_a_documented_reason(db):
    rows = db.execute(
        text(
            """
            SELECT c.conrelid::regclass::text, a.attname
            FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
            WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
              AND NOT EXISTS (
                SELECT 1 FROM pg_index i
                WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1]
              )
            """
        )
    )
    unindexed = {(table, column) for table, column in rows}
    assert unindexed - UNINDEXED_FK_ALLOWED == set(), "FK baru tanpa indeks"
    assert UNINDEXED_FK_ALLOWED - unindexed == set(), "pengecualian yang sudah tidak perlu"
