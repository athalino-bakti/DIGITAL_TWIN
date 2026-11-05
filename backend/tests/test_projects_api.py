"""DIG-97 dan DIG-99: endpoint CRUD /api/v1/data/projects terhadap PostgreSQL sungguhan.

Tes ini MENGHAPUS seluruh isi schema `public` pada database tujuan, sehingga hanya
berjalan jika `TEST_DATABASE_URL` diisi dan nama database berakhiran `_test`.
Tanpa variabel itu tes dilewati, jadi `pytest` biasa tetap tidak butuh database.

Contoh lokal (PowerShell, dari folder backend):
    docker compose exec db createdb -U puti digital_twin_test
    $env:TEST_DATABASE_URL = "postgresql+psycopg://puti:puti_local@localhost:5432/digital_twin_test"
    python -m pytest -m db -v
"""

import os
from datetime import date, timedelta
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

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DATABASE_URL belum diisi"),
]

BASE = "/api/v1/data/projects"


def project(**overrides) -> dict:
    return {
        "project_name": "Sistem Presensi Pegawai",
        "process_owner": "Urusan Kepegawaian",
        "priority_rank": 1,
        "start_date": "2026-08-24",
        "target_launch_date": "2026-12-09",
        "status": "development",
    } | overrides


@pytest.fixture(scope="module")
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


def create(client, **overrides) -> dict:
    response = client.post(BASE, json=project(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def error_fields(response) -> list[str]:
    detail = response.json()["detail"]
    if isinstance(detail, dict):
        detail = [detail]
    return [item["loc"][-1] for item in detail if "loc" in item]


# --- CRUD dasar (DIG-97) ---


def test_create_assigns_next_project_id(client):
    first = create(client, priority_rank=1)
    second = create(client, priority_rank=2)
    assert (first["project_id"], second["project_id"]) == ("PRJ-001", "PRJ-002")
    assert first["dor_fulfilled"] is False
    assert first["is_active"] is True


def test_create_with_explicit_project_id(client):
    created = create(client, project_id="PRJ-010")
    assert created["project_id"] == "PRJ-010"
    assert create(client, priority_rank=2)["project_id"] == "PRJ-011"


def test_duplicate_project_id_is_409(client):
    create(client, project_id="PRJ-005")
    response = client.post(BASE, json=project(project_id="PRJ-005", priority_rank=2))
    assert response.status_code == 409
    assert error_fields(response) == ["project_id"]


def test_list_is_sorted_by_priority(client):
    create(client, project_name="C", priority_rank=3)
    create(client, project_name="A", priority_rank=1)
    create(client, project_name="B", priority_rank=2)
    names = [p["project_name"] for p in client.get(BASE).json()]
    assert names == ["A", "B", "C"]


def test_list_filters(client):
    create(client, priority_rank=1, status="development")
    create(client, priority_rank=1, status="on_hold")
    create(client, priority_rank=2, status="released", actual_launch_date="2026-12-01")
    assert [p["status"] for p in client.get(BASE, params={"active_only": True}).json()] == [
        "development"
    ]
    on_hold = client.get(BASE, params={"status": "on_hold"}).json()
    assert [p["status"] for p in on_hold] == ["on_hold"]
    both = client.get(BASE, params=[("status", "on_hold"), ("status", "released")]).json()
    assert sorted(p["status"] for p in both) == ["on_hold", "released"]


def test_get_and_404(client):
    created = create(client)
    assert client.get(f"{BASE}/{created['project_id']}").json() == created
    assert client.get(f"{BASE}/PRJ-999").status_code == 404
    assert client.get(f"{BASE}/bukan-id").status_code == 422


def test_patch_changes_only_sent_fields(client):
    created = create(client, dor_fulfilled=True)
    response = client.patch(f"{BASE}/{created['project_id']}", json={"project_name": "SIPEG"})
    assert response.status_code == 200
    assert response.json() == created | {"project_name": "SIPEG"}


def test_patch_null_on_required_field_is_422(client):
    created = create(client)
    response = client.patch(f"{BASE}/{created['project_id']}", json={"process_owner": None})
    assert response.status_code == 422
    assert error_fields(response) == ["process_owner"]


def test_delete(client):
    created = create(client)
    assert client.delete(f"{BASE}/{created['project_id']}").status_code == 204
    assert client.get(f"{BASE}/{created['project_id']}").status_code == 404
    assert client.delete(f"{BASE}/{created['project_id']}").status_code == 404


def test_delete_project_with_tasks_is_409(client, db):
    created = create(client)
    db.execute(
        text(
            "INSERT INTO tasks (task_id, project_id, feature_name, task_name, required_role_id,"
            " complexity_id, priority_rank, estimated_days, phase, planned_start,"
            " planned_finish) VALUES ('TSK-0001', :pid, 'Presensi', 'Rancang tabel',"
            " 'ROLE-DM', 'CX-M', 1, 3, 'dm_dev', '2026-08-24', '2026-08-26')"
        ),
        {"pid": created["project_id"]},
    )
    db.commit()
    response = client.delete(f"{BASE}/{created['project_id']}")
    assert response.status_code == 409
    assert "on_hold" in response.json()["detail"]["msg"]
    assert client.get(f"{BASE}/{created['project_id']}").status_code == 200


# --- Aturan priority_rank (DIG-99) ---


def test_priority_must_be_unique_among_active_projects(client):
    first = create(client, priority_rank=1)
    response = client.post(BASE, json=project(priority_rank=1, status="planning"))
    assert response.status_code == 409
    assert error_fields(response) == ["priority_rank"]
    assert first["project_id"] in response.json()["detail"]["msg"]


@pytest.mark.parametrize(
    "inactive", [{"status": "on_hold"}, {"status": "released", "actual_launch_date": "2026-12-01"}]
)
def test_inactive_projects_do_not_hold_a_priority(client, inactive):
    create(client, priority_rank=1, **inactive)
    assert create(client, priority_rank=1)["priority_rank"] == 1


def test_patch_priority_into_clash_is_409(client):
    create(client, priority_rank=1)
    second = create(client, priority_rank=2)
    response = client.patch(f"{BASE}/{second['project_id']}", json={"priority_rank": 1})
    assert response.status_code == 409
    assert client.get(f"{BASE}/{second['project_id']}").json()["priority_rank"] == 2


def test_patch_keeping_own_priority_is_allowed(client):
    created = create(client, priority_rank=1)
    response = client.patch(f"{BASE}/{created['project_id']}", json={"status": "testing"})
    assert response.status_code == 200


def test_resuming_on_hold_project_rechecks_priority(client):
    paused = create(client, priority_rank=1, status="on_hold")
    create(client, priority_rank=1)
    response = client.patch(f"{BASE}/{paused['project_id']}", json={"status": "development"})
    assert response.status_code == 409
    response = client.patch(
        f"{BASE}/{paused['project_id']}", json={"status": "development", "priority_rank": 2}
    )
    assert response.status_code == 200


def test_database_index_catches_priority_race(client, monkeypatch):
    """Dua permintaan bersamaan sama-sama lolos cek service; index DB menolak yang kedua."""
    from app.modules.data import service

    monkeypatch.setattr(service, "ensure_unique_active_priority", lambda *args, **kwargs: None)
    create(client, priority_rank=1)
    response = client.post(BASE, json=project(priority_rank=1))
    assert response.status_code == 409
    assert error_fields(response) == ["priority_rank"]
    assert len(client.get(BASE).json()) == 1


def test_database_index_ignores_inactive_projects(client, monkeypatch):
    from app.modules.data import service

    monkeypatch.setattr(service, "ensure_unique_active_priority", lambda *args, **kwargs: None)
    create(client, priority_rank=1, status="on_hold")
    create(client, priority_rank=1, status="released", actual_launch_date="2026-12-01")
    assert create(client, priority_rank=1)["priority_rank"] == 1


@pytest.mark.parametrize("rank", [0, -3, 2_147_483_648])
def test_priority_out_of_range_is_422(client, rank):
    assert client.post(BASE, json=project(priority_rank=rank)).status_code == 422


def test_nul_in_name_is_422_on_create_and_patch(client):
    assert client.post(BASE, json=project(project_name="SIP\u0000")).status_code == 422
    created = create(client)
    response = client.patch(f"{BASE}/{created['project_id']}", json={"process_owner": "A\u0000"})
    assert response.status_code == 422
    assert error_fields(response) == ["process_owner"]


def test_patch_priority_above_integer_max_is_422(client):
    created = create(client)
    response = client.patch(f"{BASE}/{created['project_id']}", json={"priority_rank": 2**31})
    assert response.status_code == 422
    assert error_fields(response) == ["priority_rank"]


# --- Aturan actual_launch_date (DIG-99) ---


@pytest.mark.parametrize("status", ["planning", "development", "testing", "on_hold"])
def test_actual_launch_date_rejected_before_released(client, status):
    response = client.post(BASE, json=project(status=status, actual_launch_date="2026-12-01"))
    assert response.status_code == 422
    assert error_fields(response) == ["actual_launch_date"]


def test_release_flow(client):
    created = create(client)
    pid = created["project_id"]

    response = client.patch(f"{BASE}/{pid}", json={"status": "released"})
    assert response.status_code == 422
    assert error_fields(response) == ["actual_launch_date"]

    response = client.patch(
        f"{BASE}/{pid}", json={"status": "released", "actual_launch_date": "2026-12-12"}
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    # Kembali ke testing (misalnya rilis dibatalkan) wajib mengosongkan tanggal aktual.
    response = client.patch(f"{BASE}/{pid}", json={"status": "testing"})
    assert response.status_code == 422
    response = client.patch(f"{BASE}/{pid}", json={"status": "testing", "actual_launch_date": None})
    assert response.status_code == 200
    assert response.json()["actual_launch_date"] is None


def test_actual_launch_date_cannot_precede_start(client):
    response = client.post(BASE, json=project(status="released", actual_launch_date="2026-08-01"))
    assert response.status_code == 422
    assert error_fields(response) == ["actual_launch_date"]


def test_patch_start_date_after_target_is_422(client):
    created = create(client)
    response = client.patch(f"{BASE}/{created['project_id']}", json={"start_date": "2027-01-01"})
    assert response.status_code == 422
    assert error_fields(response) == ["target_launch_date"]


@pytest.mark.parametrize("value", ["01/12/2026", "14 Oct 2026", "2026/09/10", 1767225600])
def test_non_iso_dates_are_422(client, value):
    response = client.post(BASE, json=project(start_date=value))
    assert response.status_code == 422
    assert error_fields(response) == ["start_date"]


# --- Penanda pemantauan ---


def test_is_overdue_only_for_active_projects_past_target(client):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    long_ago = (date.today() - timedelta(days=90)).isoformat()
    late = create(client, priority_rank=1, start_date=long_ago, target_launch_date=yesterday)
    paused = create(
        client, priority_rank=2, status="on_hold", start_date=long_ago, target_launch_date=yesterday
    )
    on_track = create(client, priority_rank=3)
    assert late["is_overdue"] is True
    assert paused["is_overdue"] is False
    assert on_track["is_overdue"] is (date.fromisoformat("2026-12-09") < date.today())
