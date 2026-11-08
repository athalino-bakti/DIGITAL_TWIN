"""Fixture bersama untuk tes API yang memakai PostgreSQL sungguhan (marker `db`).

Fixture ini MENGHAPUS seluruh isi schema `public` pada database tujuan, sehingga
hanya berjalan jika `TEST_DATABASE_URL` diisi dan nama database berakhiran `_test`.
Tanpa variabel itu tes `db` dilewati, jadi `pytest` biasa tetap tidak butuh database.

Contoh lokal (PowerShell, dari folder backend):
    docker compose exec db createdb -U puti digital_twin_test
    $env:TEST_DATABASE_URL = "postgresql+psycopg://puti:puti_local@localhost:5432/digital_twin_test"
    python -m pytest -m db -v
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import get_db
from app.main import app

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.getenv("TEST_DATABASE_URL")

REQUIRES_DB = [
    pytest.mark.db,
    pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DATABASE_URL belum diisi"),
]


@pytest.fixture(scope="session")
def session_factory():
    url = make_url(TEST_DB_URL)
    if not (url.database or "").endswith("_test"):
        pytest.fail(
            "Nama database untuk tes harus berakhiran '_test' "
            f"(sekarang: {url.database!r}) karena isinya akan dihapus."
        )
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        config = Config(str(BACKEND_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(session_factory):
    """TestClient dengan tabel transaksi dikosongkan. Data referensi (seed) tetap ada."""
    with session_factory() as session:
        session.execute(text("TRUNCATE projects CASCADE"))
        session.commit()

    def override():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        yield session


def error_fields(response) -> list[str]:
    """Nama kolom pada `detail` error FastAPI (422 dan 409)."""
    detail = response.json()["detail"]
    if isinstance(detail, dict):
        detail = [detail]
    return [item["loc"][-1] for item in detail if "loc" in item]
