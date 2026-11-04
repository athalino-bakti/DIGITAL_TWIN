"""Tes migrasi Alembic naik dan turun terhadap PostgreSQL sungguhan.

Tes ini MENGHAPUS seluruh isi schema `public` pada database tujuan, sehingga hanya
berjalan jika `MIGRATION_TEST_DATABASE_URL` diisi dan nama database berakhiran `_test`.
Tanpa variabel itu, tes dilewati (skip) dan `pytest` biasa tetap tidak butuh database.

Contoh lokal (PowerShell, dari folder backend):
    docker compose exec db createdb -U puti digital_twin_test
    $env:MIGRATION_TEST_DATABASE_URL = "postgresql+psycopg://puti:puti_local@localhost:5432/digital_twin_test"
    python -m pytest -m migration -v
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine, make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.getenv("MIGRATION_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.migration,
    pytest.mark.skipif(not TEST_DB_URL, reason="MIGRATION_TEST_DATABASE_URL belum diisi"),
]


def make_config(connection: Connection | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def revisions_oldest_first() -> list[str]:
    script = ScriptDirectory.from_config(make_config())
    return [rev.revision for rev in reversed(list(script.walk_revisions("base", "heads")))]


def run(engine: Engine, action, *args) -> None:
    """Jalankan perintah Alembic dalam satu transaksi pada database tes."""
    with engine.begin() as connection:
        action(make_config(connection), *args)


def current_revision(engine: Engine) -> str | None:
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            return None
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def leftover_objects(engine: Engine) -> dict[str, list[str]]:
    """Objek di schema public selain tabel alembic_version.

    Enum, sequence, dan view yang lupa di-drop pada downgrade sering lolos karena
    tabelnya sudah hilang; tes mengeceknya satu per satu.
    """
    with engine.connect() as connection:
        insp = inspect(connection)
        tables = [t for t in insp.get_table_names(schema="public") if t != "alembic_version"]
        views = insp.get_view_names(schema="public")
        sequences = insp.get_sequence_names(schema="public")
        enums = [e["name"] for e in insp.get_enums(schema="public")]
    found = {"tabel": tables, "view": views, "sequence": sequences, "enum": enums}
    return {kind: names for kind, names in found.items() if names}


@pytest.fixture(scope="module")
def engine() -> Engine:
    url = make_url(TEST_DB_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail(
            "Nama database untuk tes migrasi harus berakhiran '_test' "
            f"(sekarang: {url.database!r}) karena isinya akan dihapus."
        )
    test_engine = create_engine(url, pool_pre_ping=True)
    yield test_engine
    test_engine.dispose()


@pytest.fixture(autouse=True)
def empty_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def test_only_one_head():
    heads = ScriptDirectory.from_config(make_config()).get_heads()
    assert len(heads) <= 1, (
        f"Ditemukan {len(heads)} head migrasi: {heads}. "
        "Buat merge revision dengan `alembic merge heads` sebelum digabung."
    )


def test_upgrade_downgrade_upgrade(engine: Engine):
    head = ScriptDirectory.from_config(make_config()).get_current_head()

    run(engine, command.upgrade, "head")
    assert current_revision(engine) == head

    run(engine, command.downgrade, "base")
    assert current_revision(engine) is None
    assert leftover_objects(engine) == {}, "Downgrade ke base masih menyisakan objek"

    run(engine, command.upgrade, "head")
    assert current_revision(engine) == head


def test_each_revision_can_step_down_and_up(engine: Engine):
    """Stairway test: setiap revisi bisa naik, turun satu langkah, lalu naik lagi."""
    previous = None
    for revision in revisions_oldest_first():
        run(engine, command.upgrade, revision)
        assert current_revision(engine) == revision

        run(engine, command.downgrade, "-1")
        assert current_revision(engine) == previous, f"Downgrade {revision} tidak kembali"
        if previous is None:
            assert leftover_objects(engine) == {}, f"Downgrade {revision} menyisakan objek"

        run(engine, command.upgrade, revision)
        previous = revision


def test_models_match_migrations(engine: Engine):
    """Setelah upgrade head, model SQLAlchemy tidak boleh berbeda dari skema hasil migrasi."""
    run(engine, command.upgrade, "head")
    run(engine, command.check)
