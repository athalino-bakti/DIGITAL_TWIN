"""DIG-93: tes akses per peran (RBAC) terhadap PostgreSQL sungguhan.

Butuh TEST_DATABASE_URL dengan nama basis data berakhiran `_test` (isinya dihapus).
"""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.modules.auth import security, set_roles
from app.modules.auth.dependencies import require_permission
from app.modules.auth.models import AppUser
from app.modules.auth.permissions import PERMISSION_DESCRIPTIONS, ROLES, Perm
from app.modules.auth.rbac_models import AppRole, Permission, RolePermission, UserAppRole
from app.modules.auth.router import router as auth_router
from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB

PASSWORD = "rahasia-puti-2026"

# Endpoint uji yang mewakili fitur nyata, supaya aturan akses bisa dites sebelum
# require_permission dipasang ke endpoint modul data.
probe = APIRouter(prefix="/probe")


@probe.get("/master-data", dependencies=[Depends(require_permission(Perm.MASTER_DATA_READ))])
def read_master_data() -> dict:
    return {"ok": True}


@probe.post("/master-data", dependencies=[Depends(require_permission(Perm.MASTER_DATA_WRITE))])
def write_master_data() -> dict:
    return {"ok": True}


@probe.get("/workload-all", dependencies=[Depends(require_permission(Perm.WORKLOAD_READ_ALL))])
def read_all_workload() -> dict:
    return {"ok": True}


@probe.post("/users", dependencies=[Depends(require_permission(Perm.USER_MANAGE))])
def manage_users() -> dict:
    return {"ok": True}


@probe.get("/baseline", dependencies=[Depends(require_permission(Perm.BASELINE_READ))])
def read_baseline() -> dict:
    return {"ok": True}


@probe.post("/change-events", dependencies=[Depends(require_permission(Perm.CHANGE_EVENT_WRITE))])
def write_any_change_event() -> dict:
    return {"ok": True}


@probe.post(
    "/my-change-events",
    dependencies=[Depends(require_permission(Perm.CHANGE_EVENT_WRITE_OWN))],
)
def write_own_change_event() -> dict:
    return {"ok": True}


@probe.post("/availability", dependencies=[Depends(require_permission(Perm.AVAILABILITY_WRITE))])
def write_availability() -> dict:
    return {"ok": True}


@probe.get("/event-log", dependencies=[Depends(require_permission(Perm.EVENT_LOG_EXPORT))])
def export_event_log() -> dict:
    return {"ok": True}


@probe.get("/whoami")
def whoami(
    user: Annotated[AppUser, Depends(require_permission(Perm.BASELINE_READ))],
) -> dict:
    return {"username": user.username}


@probe.get(
    "/both",
    dependencies=[Depends(require_permission(Perm.IMPORT_RUN, Perm.WORKLOAD_READ_ALL))],
)
def needs_two_permissions() -> dict:
    return {"ok": True}


# --- fixture ----------------------------------------------------------------------


# session_factory dipakai bersama dari conftest.py.


@pytest.fixture(autouse=True)
def fast_hash(monkeypatch):
    monkeypatch.setattr(security, "SCRYPT_N", 2**12)


@pytest.fixture
def db(session_factory):
    with session_factory() as session:
        session.execute(text("TRUNCATE app_user RESTART IDENTITY CASCADE"))
        session.commit()
        yield session


@pytest.fixture
def client(session_factory, db):
    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(probe)

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def make_user(db, username: str, roles: list[str]) -> AppUser:
    user = AppUser(
        username=username, full_name=username, password_hash=security.hash_password(PASSWORD)
    )
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserAppRole(user_id=user.user_id, role_code=role))
    db.commit()
    return user


def token_for(client, username: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# --- seed ---------------------------------------------------------------------------


def test_seed_matches_permission_matrix_in_code(db):
    assert set(db.scalars(select(Permission.permission_code))) == {str(p) for p in Perm}
    assert {p.permission_code: p.description for p in db.scalars(select(Permission))} == {
        str(k): v for k, v in PERMISSION_DESCRIPTIONS.items()
    }

    assert {r.role_code: (r.role_name, r.description) for r in db.scalars(select(AppRole))} == {
        code: (name, description) for code, (name, description, _) in ROLES.items()
    }
    matrix: dict[str, set[str]] = {}
    for row in db.scalars(select(RolePermission)):
        matrix.setdefault(row.role_code, set()).add(row.permission_code)
    assert matrix == {code: {str(p) for p in perms} for code, (_, _, perms) in ROLES.items()}


# --- /auth/me -------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(ROLES))
def test_me_shows_exact_permissions_of_each_role(client, db, role):
    make_user(db, "uji", [role])
    body = client.get("/api/v1/auth/me", headers=token_for(client, "uji")).json()

    assert body["roles"] == [role]
    assert set(body["permissions"]) == {str(p) for p in ROLES[role][2]}


def test_multiple_roles_give_union_of_permissions(client, db):
    make_user(db, "rangkap", ["admin_data", "kaur_asman"])
    response = client.post("/api/v1/auth/login", json={"username": "rangkap", "password": PASSWORD})
    user = response.json()["user"]

    assert user["roles"] == ["admin_data", "kaur_asman"]
    expected = ROLES["admin_data"][2] | ROLES["kaur_asman"][2]
    assert set(user["permissions"]) == {str(p) for p in expected}
    assert len(user["permissions"]) == len(set(user["permissions"])), "izin tidak boleh ganda"


def test_user_without_role_can_login_but_has_no_permission(client, db):
    make_user(db, "baru", [])
    headers = token_for(client, "baru")

    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["roles"] == [] and me.json()["permissions"] == []
    assert client.get("/probe/master-data", headers=headers).status_code == 403


# --- require_permission -------------------------------------------------------------


def test_missing_token_is_401_not_403(client, db):
    response = client.get("/probe/master-data")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_forbidden_response_is_403_with_message(client, db):
    make_user(db, "anggota", ["anggota_tim"])
    response = client.post("/probe/master-data", headers=token_for(client, "anggota"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Anda tidak punya izin untuk tindakan ini"


ACCESS_CASES = [
    # (peran, endpoint, method, boleh?)
    ("anggota_tim", "/probe/master-data", "get", True),
    ("anggota_tim", "/probe/master-data", "post", False),
    ("anggota_tim", "/probe/workload-all", "get", False),
    ("anggota_tim", "/probe/users", "post", False),
    # FR-08 sampai FR-11: baseline hanya untuk Kaur/Asman dan System Analyst.
    ("anggota_tim", "/probe/baseline", "get", False),
    # FR-05 dan Tabel 2.1: anggota hanya mencatat kejadian pada task miliknya.
    ("anggota_tim", "/probe/my-change-events", "post", True),
    ("anggota_tim", "/probe/change-events", "post", False),
    # FR-06: ketidakhadiran dan rotasi hanya Kaur/Asman dan System Analyst.
    ("anggota_tim", "/probe/availability", "post", False),
    ("kaur_asman", "/probe/workload-all", "get", True),
    ("kaur_asman", "/probe/baseline", "get", True),
    ("kaur_asman", "/probe/change-events", "post", True),
    ("kaur_asman", "/probe/availability", "post", True),
    ("kaur_asman", "/probe/master-data", "post", False),
    ("kaur_asman", "/probe/users", "post", False),
    ("system_analyst", "/probe/workload-all", "get", True),
    ("system_analyst", "/probe/change-events", "post", True),
    ("system_analyst", "/probe/availability", "post", True),
    ("system_analyst", "/probe/master-data", "post", False),
    # FR-07: ekspor event log untuk Administrator Data dan System Analyst (DIG-39).
    ("system_analyst", "/probe/event-log", "get", True),
    ("admin_data", "/probe/event-log", "get", True),
    ("admin_data", "/probe/master-data", "post", True),
    # Pengelolaan akun milik Admin IT, bukan Administrator Data.
    ("admin_data", "/probe/users", "post", False),
    # Data beban seluruh anggota hanya untuk Kaur/Asman dan System Analyst (DIG-19).
    ("admin_data", "/probe/workload-all", "get", False),
    ("admin_data", "/probe/change-events", "post", False),
    ("admin_it", "/probe/users", "post", True),
    ("admin_it", "/probe/master-data", "get", False),
    ("admin_it", "/probe/workload-all", "get", False),
]


@pytest.mark.parametrize(("role", "path", "method", "allowed"), ACCESS_CASES)
def test_access_per_role(client, db, role, path, method, allowed):
    make_user(db, "uji", [role])
    response = getattr(client, method)(path, headers=token_for(client, "uji"))
    assert response.status_code == (200 if allowed else 403)


def test_permissions_never_leak_between_users(client, db):
    """Izin admin tidak boleh ikut terbawa ke user lain yang login bersamaan."""
    make_user(db, "admin", ["admin_it"])
    make_user(db, "anggota", ["anggota_tim"])
    make_user(db, "kaur", ["kaur_asman"])
    admin, anggota, kaur = (token_for(client, u) for u in ("admin", "anggota", "kaur"))

    assert client.post("/probe/users", headers=admin).status_code == 200
    assert client.post("/probe/users", headers=anggota).status_code == 403
    assert client.post("/probe/users", headers=kaur).status_code == 403
    assert client.get("/probe/workload-all", headers=kaur).status_code == 200
    assert client.get("/probe/workload-all", headers=admin).status_code == 403
    assert client.get("/probe/workload-all", headers=anggota).status_code == 403

    me = client.get("/api/v1/auth/me", headers=anggota).json()
    assert set(me["permissions"]) == {str(p) for p in ROLES["anggota_tim"][2]}


def test_dependency_returns_current_user(client, db):
    make_user(db, "kaur", ["kaur_asman"])
    response = client.get("/probe/whoami", headers=token_for(client, "kaur"))
    assert response.json() == {"username": "kaur"}


def test_all_requested_permissions_are_required(client, db):
    make_user(db, "admin", ["admin_data"])  # punya import:run, tidak punya workload:read_all
    assert client.get("/probe/both", headers=token_for(client, "admin")).status_code == 403

    make_user(db, "lengkap", ["admin_data", "system_analyst"])
    assert client.get("/probe/both", headers=token_for(client, "lengkap")).status_code == 200


def test_role_change_applies_without_relogin(client, db):
    user = make_user(db, "rotasi", ["admin_data"])
    headers = token_for(client, "rotasi")
    assert client.post("/probe/master-data", headers=headers).status_code == 200

    db.execute(delete(UserAppRole).where(UserAppRole.user_id == user.user_id))
    db.add(UserAppRole(user_id=user.user_id, role_code="anggota_tim"))
    db.commit()

    assert client.post("/probe/master-data", headers=headers).status_code == 403
    assert client.get("/probe/master-data", headers=headers).status_code == 200


def test_deactivated_user_with_role_is_401(client, db):
    user = make_user(db, "nonaktif", ["admin_data"])
    headers = token_for(client, "nonaktif")
    user.is_active = False
    db.commit()

    assert client.post("/probe/master-data", headers=headers).status_code == 401


def test_require_permission_rejects_empty_or_unknown_codes():
    with pytest.raises(ValueError):
        require_permission()
    with pytest.raises(ValueError):
        require_permission("izin:palsu")


# --- integritas data ------------------------------------------------------------------


def test_deleting_user_removes_its_role_assignments(db):
    user = make_user(db, "hapus", ["kaur_asman", "admin_data"])
    db.delete(user)
    db.commit()
    assert db.scalar(select(UserAppRole).where(UserAppRole.user_id == user.user_id)) is None


def test_role_in_use_cannot_be_deleted(db):
    make_user(db, "pakai", ["kaur_asman"])
    with pytest.raises(IntegrityError):
        db.execute(delete(AppRole).where(AppRole.role_code == "kaur_asman"))
        db.commit()
    db.rollback()


def test_unknown_role_cannot_be_assigned(db):
    user = make_user(db, "salah", [])
    db.add(UserAppRole(user_id=user.user_id, role_code="raja"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- CLI set_roles -------------------------------------------------------------------------


@pytest.fixture
def cli_db(session_factory, monkeypatch):
    monkeypatch.setattr(set_roles, "SessionLocal", session_factory)


def roles_of(db, username: str) -> list[str]:
    db.expire_all()
    user = db.scalar(select(AppUser).where(AppUser.username == username))
    return sorted(
        db.scalars(select(UserAppRole.role_code).where(UserAppRole.user_id == user.user_id))
    )


def test_cli_assigns_and_replaces_roles(db, cli_db, capsys):
    make_user(db, "bagas", ["anggota_tim"])

    assert (
        set_roles.main(["--username", "Bagas", "--role", "admin_data", "--role", "system_analyst"])
        == 0
    )
    assert roles_of(db, "bagas") == ["admin_data", "system_analyst"]

    assert set_roles.main(["--username", "bagas", "--clear"]) == 0
    assert roles_of(db, "bagas") == []
    assert "tanpa peran" in capsys.readouterr().out


def test_cli_rejects_unknown_role_and_user(db, cli_db, capsys):
    make_user(db, "bagas", ["anggota_tim"])

    assert set_roles.main(["--username", "bagas", "--role", "raja"]) == 1
    assert roles_of(db, "bagas") == ["anggota_tim"], "peran lama tidak boleh berubah"
    assert set_roles.main(["--username", "hantu", "--role", "admin_data"]) == 1
    assert "tidak dikenal" in capsys.readouterr().err


def test_cli_rejects_clear_together_with_role(db, cli_db, capsys):
    make_user(db, "bagas", ["anggota_tim"])

    assert set_roles.main(["--username", "bagas", "--clear", "--role", "admin_data"]) == 1
    assert roles_of(db, "bagas") == ["anggota_tim"], "peran lama tidak boleh berubah"
    assert "salah satu" in capsys.readouterr().err


def test_cli_lists_available_roles(db, cli_db, capsys):
    assert set_roles.main(["--list"]) == 0
    out = capsys.readouterr().out
    for code in ROLES:
        assert code in out
