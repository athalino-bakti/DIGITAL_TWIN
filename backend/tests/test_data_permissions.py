"""DIG-226: setiap endpoint /api/v1/data wajib login dan izin yang sesuai peran."""

import pytest
from fastapi.routing import APIRoute

from app.main import app
from app.modules.auth.permissions import Perm
from tests.conftest import REQUIRES_DB, make_token

DATA_PREFIX = "/api/v1/data"


def requires_db(test):
    for mark in REQUIRES_DB:
        test = mark(test)
    return test


# Peta izin yang disepakati. Endpoint data baru wajib ditambahkan di sini.
EXPECTED = {
    ("GET", "/projects"): Perm.MASTER_DATA_READ,
    ("POST", "/projects"): Perm.MASTER_DATA_WRITE,
    ("GET", "/projects/{project_id}"): Perm.MASTER_DATA_READ,
    ("PATCH", "/projects/{project_id}"): Perm.MASTER_DATA_WRITE,
    ("DELETE", "/projects/{project_id}"): Perm.MASTER_DATA_WRITE,
    # D-10 kejadian perubahan (DIG-149): FR-05.
    ("GET", "/change-events"): Perm.WORKLOAD_READ_ALL,
    ("GET", "/change-events/{event_id}"): Perm.WORKLOAD_READ_ALL,
    ("POST", "/change-events"): Perm.CHANGE_EVENT_WRITE,
    ("PATCH", "/change-events/{event_id}"): Perm.CHANGE_EVENT_WRITE,
    ("DELETE", "/change-events/{event_id}"): Perm.CHANGE_EVENT_WRITE,
    # "Task saya" (DIG-153): blocker dan overrun oleh pelaksana task; deteksi otomatis DIG-154.
    ("GET", "/my-tasks"): Perm.WORKLOAD_READ_OWN,
    ("POST", "/my-tasks/{task_id}/events"): Perm.CHANGE_EVENT_WRITE_OWN,
    ("POST", "/my-tasks/{task_id}/events/{event_id}/resolve"): Perm.CHANGE_EVENT_WRITE_OWN,
    ("POST", "/overrun-detection"): Perm.CHANGE_EVENT_WRITE,
    ("GET", "/complexity-levels"): Perm.MASTER_DATA_READ,
    ("PATCH", "/complexity-levels/{complexity_id}"): Perm.MASTER_DATA_WRITE,
    ("GET", "/resources"): Perm.MASTER_DATA_READ,
    ("POST", "/resources"): Perm.MASTER_DATA_WRITE,
    ("GET", "/resources/{resource_id}"): Perm.MASTER_DATA_READ,
    ("PATCH", "/resources/{resource_id}"): Perm.MASTER_DATA_WRITE,
    ("DELETE", "/resources/{resource_id}"): Perm.MASTER_DATA_WRITE,
    ("GET", "/roles"): Perm.MASTER_DATA_READ,
    ("PATCH", "/roles/{role_id}"): Perm.MASTER_DATA_WRITE,
    # D-05 tasks (DIG-161).
    ("GET", "/tasks"): Perm.MASTER_DATA_READ,
    ("GET", "/tasks/{task_id}"): Perm.MASTER_DATA_READ,
    ("PATCH", "/tasks/{task_id}/status"): Perm.MASTER_DATA_WRITE,
    ("GET", "/availability"): Perm.WORKLOAD_READ_ALL,
    ("POST", "/availability"): Perm.AVAILABILITY_WRITE,
    ("PATCH", "/availability/{availability_id}"): Perm.AVAILABILITY_WRITE,
    ("DELETE", "/availability/{availability_id}"): Perm.AVAILABILITY_WRITE,
    # Pengalihan task saat anggota tidak hadir (DIG-35): FR-06 dan DIG-19.
    ("GET", "/availability/{availability_id}/affected-tasks"): Perm.WORKLOAD_READ_ALL,
    ("GET", "/tasks/{task_id}/assignments"): Perm.WORKLOAD_READ_ALL,
    ("GET", "/tasks/{task_id}/replacement-candidates"): Perm.WORKLOAD_READ_ALL,
    ("POST", "/tasks/{task_id}/takeover"): Perm.AVAILABILITY_WRITE,
    ("GET", "/holidays"): Perm.MASTER_DATA_READ,
    ("POST", "/holidays"): Perm.MASTER_DATA_WRITE,
    ("PATCH", "/holidays/{holiday_date}"): Perm.MASTER_DATA_WRITE,
    ("DELETE", "/holidays/{holiday_date}"): Perm.MASTER_DATA_WRITE,
    ("GET", "/workload-items"): Perm.WORKLOAD_READ_ALL,
    ("POST", "/workload-items"): Perm.MASTER_DATA_WRITE,
    ("POST", "/workload-items/import"): Perm.IMPORT_RUN,
    ("PATCH", "/workload-items/{item_id}"): Perm.MASTER_DATA_WRITE,
    ("DELETE", "/workload-items/{item_id}"): Perm.MASTER_DATA_WRITE,
    # Event log (DIG-37): membentuk ulang = pengolahan impor, membaca = ekspor (FR-07).
    ("POST", "/event-log/rebuild"): Perm.IMPORT_RUN,
    ("GET", "/event-log"): Perm.EVENT_LOG_EXPORT,
    # Pemantauan job impor terjadwal (DIG-128).
    ("GET", "/import-jobs"): Perm.DATA_QUALITY_READ,
    ("GET", "/import-jobs/{job_id}"): Perm.DATA_QUALITY_READ,
    # Alias identitas (DIG-24): memuat username dan email anggota, jadi Administrator Data saja.
    ("GET", "/resource-aliases"): Perm.MASTER_DATA_WRITE,
    ("GET", "/resource-aliases/unmapped"): Perm.MASTER_DATA_WRITE,
    ("POST", "/resource-aliases"): Perm.MASTER_DATA_WRITE,
    ("PATCH", "/resource-aliases/{alias_id}"): Perm.MASTER_DATA_WRITE,
    ("DELETE", "/resource-aliases/{alias_id}"): Perm.MASTER_DATA_WRITE,
    # Unggah Project Plan ke staging (DIG-25), sama dengan impor lain.
    ("POST", "/imports/project-plan"): Perm.IMPORT_RUN,
    # Pemetaan list Trello (DIG-120): konfigurasi impor.
    ("GET", "/trello-lists"): Perm.IMPORT_RUN,
    ("PATCH", "/trello-lists/{board_id}/{list_id}"): Perm.IMPORT_RUN,
    # Laporan kualitas data dan baris ditolak per impor (DIG-146).
    ("GET", "/quality/summary"): Perm.DATA_QUALITY_READ,
    ("GET", "/quality/summary.csv"): Perm.DATA_QUALITY_READ,
    ("GET", "/quality/rejected-rows"): Perm.DATA_QUALITY_READ,
    ("GET", "/quality/rejected-rows.csv"): Perm.DATA_QUALITY_READ,
}


def required_permissions(dependant) -> set[Perm]:
    found: set[Perm] = set(getattr(dependant.call, "required_permissions", ()))
    for sub in dependant.dependencies:
        found |= required_permissions(sub)
    return found


def walk(routes, prefix: str = "", inherited: frozenset = frozenset()):
    """Semua APIRoute beserta path lengkapnya, menelusuri router yang di-include bertingkat."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefix + route.path, route, inherited
        elif hasattr(route, "original_router"):
            context = route.include_context
            extra = frozenset(
                perm
                for dependency in context.dependencies
                for perm in getattr(dependency.dependency, "required_permissions", ())
            )
            yield from walk(
                route.original_router.routes, prefix + context.prefix, inherited | extra
            )


def data_routes() -> dict[tuple[str, str], set[Perm]]:
    """Semua endpoint berawalan /api/v1/data, dari router mana pun asalnya.

    Ditelusuri dari aplikasi FastAPI itu sendiri, jadi router yang dipasang di app/main.py,
    di app/api/router.py, atau di-include ke router data semuanya ikut diperiksa.
    """
    routes = {}
    for path, route, inherited in walk(app.routes):
        if not path.startswith(DATA_PREFIX + "/"):
            continue
        for method in route.methods:
            key = (method, path.removeprefix(DATA_PREFIX))
            routes[key] = set(inherited) | required_permissions(route.dependant)
    return routes


def test_route_walker_finds_the_data_router():
    assert len(data_routes()) >= len(EXPECTED)


# --- tanpa basis data -----------------------------------------------------------------


def test_every_data_endpoint_requires_a_permission():
    """Penjaga: endpoint data baru tanpa require_permission langsung ketahuan di CI."""
    unprotected = sorted(key for key, perms in data_routes().items() if not perms)
    assert unprotected == []


def test_data_endpoints_use_the_agreed_permission():
    actual = data_routes()
    assert set(actual) == set(EXPECTED), "endpoint data baru wajib dicatat di EXPECTED"
    assert actual == {key: {perm} for key, perm in EXPECTED.items()}


# --- lewat HTTP -----------------------------------------------------------------------


def as_role(client, db, role: str | None) -> dict:
    if role is None:
        return {"Authorization": ""}
    return {"Authorization": f"Bearer {make_token(db, f'uji_{role}', [role])}"}


CASES = [
    # (peran, method, path, body, boleh?)
    (None, "get", "/projects", None, False),
    ("admin_it", "get", "/projects", None, False),
    ("anggota_tim", "get", "/projects", None, True),
    ("anggota_tim", "post", "/projects", {}, False),
    ("kaur_asman", "post", "/projects", {}, False),
    ("admin_data", "post", "/projects", {}, True),
    ("anggota_tim", "get", "/roles", None, True),
    ("system_analyst", "patch", "/roles/ROLE-BE", {}, False),
    ("admin_data", "patch", "/roles/ROLE-BE", {}, True),
    # D-10: dicatat Kaur/Asman dan System Analyst (FR-05).
    ("anggota_tim", "get", "/change-events", None, False),
    ("kaur_asman", "get", "/change-events", None, True),
    ("anggota_tim", "post", "/change-events", {}, False),
    ("admin_data", "post", "/change-events", {}, False),
    ("kaur_asman", "post", "/change-events", {}, True),
    ("system_analyst", "delete", "/change-events/EVT-999", None, True),
    # D-09: data ketidakhadiran seluruh anggota (DIG-19) dan FR-06.
    ("anggota_tim", "get", "/availability", None, False),
    ("admin_data", "get", "/availability", None, False),
    ("kaur_asman", "get", "/availability", None, True),
    ("system_analyst", "get", "/availability", None, True),
    ("admin_data", "post", "/availability", {}, False),
    ("kaur_asman", "post", "/availability", {}, True),
    ("system_analyst", "delete", "/availability/AVL-999", None, True),
    # Pengalihan task (DIG-35).
    ("anggota_tim", "get", "/tasks/TSK-9999/assignments", None, False),
    ("system_analyst", "get", "/tasks/TSK-9999/assignments", None, True),
    ("anggota_tim", "get", "/tasks/TSK-9999/replacement-candidates", None, False),
    ("kaur_asman", "get", "/tasks/TSK-9999/replacement-candidates", None, True),
    ("admin_data", "post", "/tasks/TSK-9999/takeover", {}, False),
    ("kaur_asman", "post", "/tasks/TSK-9999/takeover", {}, True),
    ("anggota_tim", "get", "/availability/AVL-999/affected-tasks", None, False),
    ("system_analyst", "get", "/availability/AVL-999/affected-tasks", None, True),
    ("anggota_tim", "get", "/holidays", None, True),
    ("anggota_tim", "delete", "/holidays/2026-12-25", None, False),
    # D-05 status task (DIG-161).
    ("anggota_tim", "get", "/tasks", None, True),
    ("anggota_tim", "patch", "/tasks/TSK-9999/status", {}, False),
    ("system_analyst", "patch", "/tasks/TSK-9999/status", {}, False),
    ("admin_data", "patch", "/tasks/TSK-9999/status", {}, True),
    ("admin_data", "delete", "/holidays/2026-12-25", None, True),
    # D-08: beban non-proyek per orang (DIG-19), input dan impor oleh Administrator Data.
    ("anggota_tim", "get", "/workload-items", None, False),
    ("admin_data", "get", "/workload-items", None, False),
    ("kaur_asman", "get", "/workload-items", None, True),
    ("system_analyst", "get", "/workload-items", None, True),
    ("system_analyst", "post", "/workload-items", {}, False),
    ("admin_data", "post", "/workload-items", {}, True),
    ("admin_data", "delete", "/workload-items/WLI-9999", None, True),
    ("kaur_asman", "post", "/workload-items/import", {"content": "", "dry_run": True}, False),
    ("admin_data", "post", "/workload-items/import", {"content": "", "dry_run": True}, True),
    ("anggota_tim", "post", "/imports/project-plan", {}, False),
    ("kaur_asman", "post", "/imports/project-plan", {}, False),
    ("admin_data", "post", "/imports/project-plan", {}, True),
    # DIG-153: task saya untuk semua yang punya beban sendiri; mencatat hanya anggota tim.
    ("admin_data", "get", "/my-tasks", None, False),
    ("anggota_tim", "get", "/my-tasks", None, True),
    ("kaur_asman", "get", "/my-tasks", None, True),
    ("system_analyst", "post", "/my-tasks/TSK-9999/events", {"event_type": "blocker"}, False),
    ("anggota_tim", "post", "/my-tasks/TSK-9999/events", {"event_type": "blocker"}, True),
    ("anggota_tim", "post", "/my-tasks/TSK-9999/events/EVT-999/resolve", {}, True),
    ("anggota_tim", "post", "/overrun-detection", None, False),
    ("admin_data", "post", "/overrun-detection", None, False),
    ("system_analyst", "post", "/overrun-detection", None, True),
    # DIG-24: alias identitas hanya untuk Administrator Data.
    ("anggota_tim", "get", "/resource-aliases", None, False),
    ("system_analyst", "get", "/resource-aliases/unmapped", None, False),
    ("admin_data", "get", "/resource-aliases/unmapped", None, True),
    ("kaur_asman", "post", "/resource-aliases", {}, False),
    ("admin_data", "post", "/resource-aliases", {}, True),
    ("admin_data", "delete", "/resource-aliases/999999", None, True),
]


@requires_db
def test_system_analyst_who_is_also_admin_data_can_see_and_input_workload(client, db):
    """Peran Administrator Data di PuTI dipegang SA sebagai peran kedua (Tabel 2.1)."""
    token = make_token(db, "sa_admin", ["system_analyst", "admin_data"])
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get(f"{DATA_PREFIX}/workload-items", headers=headers).status_code == 200
    response = client.post(f"{DATA_PREFIX}/workload-items", headers=headers, json={})
    assert response.status_code == 422  # lolos izin, ditolak validasi body kosong


@requires_db
@pytest.mark.parametrize(("role", "method", "path", "body", "allowed"), CASES)
def test_access_per_role(client, db, role, method, path, body, allowed):
    kwargs = {"headers": as_role(client, db, role)}
    if body is not None:
        kwargs["json"] = body
    response = client.request(method.upper(), f"{DATA_PREFIX}{path}", **kwargs)

    if allowed:
        # Lolos izin; hasil berikutnya urusan validasi atau data (200, 201, 404, 422).
        assert response.status_code not in (401, 403), response.text
    else:
        assert response.status_code == (401 if role is None else 403), response.text


@requires_db
def test_permission_is_checked_before_body_validation(client):
    """Tanpa token, body yang salah tidak sempat divalidasi (401, bukan 422)."""
    del client.headers["Authorization"]
    response = client.post(f"{DATA_PREFIX}/projects", json={"project_name": ""})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@requires_db
def test_health_stays_public(client):
    del client.headers["Authorization"]
    assert client.get("/api/v1/health").status_code == 200
