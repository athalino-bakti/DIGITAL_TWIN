"""DIG-88: login berhasil, gagal, dan token kedaluwarsa terhadap PostgreSQL sungguhan.

Tes ini MENGHAPUS seluruh isi schema `public` pada database tujuan, sehingga hanya
berjalan jika `TEST_DATABASE_URL` diisi dan nama database berakhiran `_test`.

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
from app.modules.auth import rate_limit, security
from app.modules.auth.models import AppUser
from app.modules.auth.rate_limit import LoginRateLimiter

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DB_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.db,
    pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DATABASE_URL belum diisi"),
]

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
PASSWORD = "rahasia-puti-2026"
WRONG_LOGIN = "Username atau password salah"


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


@pytest.fixture(autouse=True)
def fast_hash(monkeypatch):
    # Hash di tes memakai N lebih kecil supaya cepat. verify_password membaca parameter
    # dari hash yang tersimpan, jadi alurnya tetap sama dengan produksi.
    monkeypatch.setattr(security, "SCRYPT_N", 2**12)
    monkeypatch.setattr(security, "_dummy_hash", None)
    # Hitungan login gagal tidak boleh terbawa dari tes sebelumnya.
    rate_limit.get_login_limiter().reset()


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        session.execute(text("TRUNCATE app_user RESTART IDENTITY CASCADE"))
        session.commit()
        yield session


@pytest.fixture
def client(session_factory, db):
    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def make_user(db, username="bagas", password=PASSWORD, is_active=True, full_name="Bagas"):
    user = AppUser(
        username=username,
        full_name=full_name,
        password_hash=security.hash_password(password),
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    return user


def login(client, username="bagas", password=PASSWORD):
    return client.post(LOGIN, json={"username": username, "password": password})


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- login berhasil -------------------------------------------------------------


def test_login_success_returns_token_and_user(client, db):
    user = make_user(db)

    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 60 * 60
    assert body["user"]["user_id"] == user.user_id
    assert body["user"]["username"] == "bagas"
    assert "password_hash" not in body["user"]
    assert security.decode_access_token(body["access_token"]) == user.user_id


def test_login_records_last_login(client, db):
    user = make_user(db)
    assert user.last_login_at is None

    login(client)

    db.refresh(user)
    assert user.last_login_at is not None


def test_login_username_is_case_and_space_insensitive(client, db):
    make_user(db)
    assert login(client, username="  Bagas ").status_code == 200


def test_me_returns_logged_in_user(client, db):
    make_user(db, full_name="Bagas Haris Saputro")
    token = login(client).json()["access_token"]

    response = client.get(ME, headers=bearer(token))

    assert response.status_code == 200
    assert response.json()["full_name"] == "Bagas Haris Saputro"
    assert response.json()["last_login_at"] is not None


# --- login gagal ----------------------------------------------------------------


def test_wrong_password_is_rejected(client, db):
    make_user(db)
    response = login(client, password="salah-password")

    assert response.status_code == 401
    assert response.json()["detail"] == WRONG_LOGIN
    assert response.headers["www-authenticate"] == "Bearer"


def test_unknown_user_gets_same_message_as_wrong_password(client, db):
    make_user(db)
    response = login(client, username="tidak-ada")

    assert response.status_code == 401
    assert response.json()["detail"] == WRONG_LOGIN


def test_inactive_user_cannot_login(client, db):
    make_user(db, is_active=False)
    response = login(client)

    assert response.status_code == 401
    assert response.json()["detail"] == WRONG_LOGIN


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "bagas"},
        {"password": PASSWORD},
        {"username": "", "password": PASSWORD},
        {"username": "bagas", "password": ""},
        {"username": "bagas", "password": "x" * 257},
        {"username": "bagas", "password": PASSWORD, "role": "admin"},
    ],
)
def test_invalid_login_body_is_422(client, db, payload):
    make_user(db)
    assert client.post(LOGIN, json=payload).status_code == 422


# --- token tidak sah dan kedaluwarsa ---------------------------------------------


def test_me_without_token_is_401(client, db):
    response = client.get(ME)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "header",
    ["Bearer bukan-token", "Bearer ", "Basic YmFnYXM6cmFoYXNpYQ==", "bagas"],
)
def test_me_with_malformed_token_is_401(client, db, header):
    make_user(db)
    assert client.get(ME, headers={"Authorization": header}).status_code == 401


def test_expired_token_is_401(client, db):
    user = make_user(db)
    expired = security.create_access_token(user.user_id, user.username, expires_minutes=-1)

    assert client.get(ME, headers=bearer(expired)).status_code == 401


def test_tampered_token_is_401(client, db):
    make_user(db)
    token = login(client).json()["access_token"]
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'AA' if signature[-2:] != 'AA' else 'BB'}"

    assert client.get(ME, headers=bearer(tampered)).status_code == 401


def test_token_of_deactivated_user_stops_working(client, db):
    user = make_user(db)
    token = login(client).json()["access_token"]
    assert client.get(ME, headers=bearer(token)).status_code == 200

    user.is_active = False
    db.commit()

    assert client.get(ME, headers=bearer(token)).status_code == 401


def test_token_of_deleted_user_is_401(client, db):
    user = make_user(db)
    token = login(client).json()["access_token"]

    db.delete(user)
    db.commit()

    assert client.get(ME, headers=bearer(token)).status_code == 401


# --- batas percobaan login dan beban hash -----------------------------------------


TOO_MANY = "Terlalu banyak percobaan login"


def test_account_is_locked_after_five_wrong_passwords(client, db):
    make_user(db)
    make_user(db, username="davi")
    for _ in range(5):
        assert login(client, password="salah-password").status_code == 401

    response = login(client)  # password benar pun ditolak selama terkunci

    assert response.status_code == 429
    assert response.json()["detail"].startswith(TOO_MANY)
    assert 1 <= int(response.headers["retry-after"]) <= 15 * 60
    assert login(client, username="davi").status_code == 200, "akun lain tidak ikut terkunci"


def test_unknown_username_is_locked_the_same_way(client, db):
    """Respons 429 tidak boleh membedakan username terdaftar dan tidak."""
    make_user(db)
    for username in ("bagas", "hantu"):
        for _ in range(5):
            login(client, username=username, password="salah-password")
    known = login(client, username="bagas", password="salah-password")
    unknown = login(client, username="hantu", password="salah-password")

    assert known.status_code == unknown.status_code == 429
    assert known.json() == unknown.json()


def test_successful_login_resets_the_counter(client, db):
    make_user(db)
    for _ in range(4):
        login(client, password="salah-password")
    assert login(client).status_code == 200
    for _ in range(4):
        assert login(client, password="salah-password").status_code == 401


def test_locked_login_does_not_hash_the_password(client, db, monkeypatch):
    make_user(db)
    for _ in range(5):
        login(client, password="salah-password")
    calls = []
    monkeypatch.setattr(security, "verify_password", lambda *args: calls.append(args))
    monkeypatch.setattr(security, "burn_password_check", lambda *args: calls.append(args))

    assert login(client).status_code == 429
    assert calls == [], "login yang ditolak 429 tidak boleh menghitung hash"


def test_one_ip_trying_many_usernames_is_limited(client, db, monkeypatch):
    monkeypatch.setattr(
        rate_limit, "_limiter", LoginRateLimiter(max_per_user=5, max_per_ip=3, window_seconds=900)
    )
    make_user(db)
    for username in ("andi", "budi", "citra"):
        assert login(client, username=username, password="salah-password").status_code == 401

    assert login(client).status_code == 429


def test_busy_hash_slots_give_503_and_do_not_count_as_failure(client, db, monkeypatch):
    make_user(db)

    def busy(*args, **kwargs):
        raise security.HashBusyError

    monkeypatch.setattr(security, "_scrypt", busy)
    for _ in range(6):
        response = login(client)
        assert response.status_code == 503
        assert response.headers["retry-after"] == "5"
    monkeypatch.undo()
    monkeypatch.setattr(security, "SCRYPT_N", 2**12)

    assert login(client).status_code == 200


def test_login_upgrades_hash_with_old_parameters(client, db, monkeypatch):
    monkeypatch.setattr(security, "SCRYPT_N", 2**11)
    user = make_user(db)
    monkeypatch.setattr(security, "SCRYPT_N", 2**12)
    assert security.needs_rehash(user.password_hash)

    assert login(client).status_code == 200

    db.refresh(user)
    assert user.password_hash.startswith(f"scrypt${2**12}$8$3$")
    assert not security.needs_rehash(user.password_hash)
    assert login(client).status_code == 200
