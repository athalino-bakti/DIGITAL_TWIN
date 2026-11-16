"""DIG-49: memuat data sintetis ke basis data staging."""

from datetime import date

import pytest
from sqlalchemy import text

from synthetic import load as loader
from synthetic.final_sources import final_source_rows
from synthetic.world import build_world
from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB
AS_OF = date(2026, 11, 6)


@pytest.fixture
def empty(session_factory):
    """D-01 sampai D-11 kosong, roles dan complexity_levels tetap berisi seed migrasi.

    Semua di dalam satu transaksi yang di-rollback, jadi tes lain tidak terpengaruh."""
    session = session_factory()
    connection = session.connection()
    connection.execute(
        text(
            "TRUNCATE change_events, availability, workload_items, assignments,"
            " task_dependencies, tasks, resources, projects, holidays CASCADE"
        )
    )
    yield connection
    session.rollback()
    session.close()


def counts(connection) -> dict[str, int]:
    return {
        name: connection.execute(text(f"SELECT count(*) FROM {name}")).scalar()
        for name in loader.LOAD_ORDER
    }


def test_loads_every_final_source_and_keeps_migration_seeds(empty):
    expected = {k: len(v) for k, v in final_source_rows(build_world(42, AS_OF)).items()}
    before = counts(empty)

    inserted = loader.load(empty, 42, AS_OF)

    after = counts(empty)
    for name in loader.LOAD_ORDER:
        if name in loader.SEEDED:
            # ID sintetis sama dengan seed migrasi 0005, jadi tidak ada yang ditimpa.
            assert inserted[name] == 0
            assert after[name] == before[name]
        else:
            assert after[name] == expected[name] == inserted[name]
    assert after["tasks"] == 136


def test_refuses_database_that_already_has_data(empty):
    loader.load(empty, 42, AS_OF)
    with pytest.raises(loader.NotEmptyError, match="projects 5 baris"):
        loader.load(empty, 7, AS_OF)


@pytest.fixture
def fresh_settings():
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_refuses_production(monkeypatch, capsys, fresh_settings):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 48)
    assert loader.main([]) == 2
    assert "APP_ENV=production" in capsys.readouterr().err


def test_refuses_production_set_only_in_dotenv(monkeypatch, tmp_path, capsys, fresh_settings):
    """APP_ENV yang hanya ada di berkas .env juga dikenali (review #42)."""
    from app.core import config

    env_file = tmp_path / ".env"
    env_file.write_text(f"APP_ENV=production\nJWT_SECRET_KEY={'y' * 48}\n", encoding="utf-8")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setitem(config.Settings.model_config, "env_file", env_file)
    assert loader.main([]) == 2
    assert "APP_ENV=production" in capsys.readouterr().err
