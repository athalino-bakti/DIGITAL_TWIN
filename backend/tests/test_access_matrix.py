"""DIG-207 (story DIG-50): matriks uji akses per peran untuk SEMUA endpoint API.

`test_data_permissions.py` menjaga izin endpoint /api/v1/data. Berkas ini melengkapinya:
- endpoint di luar /data (auth, health, Digital Twin) juga wajib tercatat dan berizin;
- setiap endpoint dipanggil lewat HTTP tanpa login dan sebagai kelima peran aplikasi, lalu
  jawabannya dibandingkan dengan matriks yang dibaca dari kode (app/qa/access_matrix.py).
"""

import re

import pytest

from app.main import app
from app.modules.auth.permissions import ROLES, Perm
from app.qa.access_matrix import ANY_OF, LOGIN_ONLY, PUBLIC, access_rules, role_permissions
from tests.conftest import REQUIRES_DB, make_token
from tests.test_data_permissions import DATA_PREFIX
from tests.test_data_permissions import EXPECTED as DATA_EXPECTED

RULES = access_rules(app)

# Endpoint di luar /api/v1/data dan izinnya. Endpoint baru di luar /data wajib dicatat di sini.
OTHER_EXPECTED: dict[tuple[str, str], frozenset[Perm]] = {
    ("GET", "/api/v1/digital-twin/summary"): frozenset({Perm.BASELINE_READ}),
    ("GET", "/api/v1/digital-twin/timeline"): frozenset({Perm.BASELINE_READ}),
    ("GET", "/api/v1/digital-twin/dependency"): frozenset({Perm.BASELINE_READ}),
    ("GET", "/api/v1/digital-twin/process-map"): frozenset({Perm.BASELINE_READ}),
}

# Nilai contoh untuk parameter path. Izin diperiksa sebelum isi permintaan, sehingga peran
# tanpa izin selalu mendapat 403; peran berizin boleh mendapat 404 atau 422.
PATH_VALUES = {
    "project_id": "PRJ-999",
    "task_id": "TSK-9999",
    "resource_id": "RES-999",
    "role_id": "ROLE-BE",
    "complexity_id": "CX-M",
    "event_id": "EVT-999",
    "availability_id": "AVL-999",
    "item_id": "WLI-9999",
    "holiday_date": "2026-12-25",
}
DEFAULT_PATH_VALUE = "999999"


def concrete(path: str) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: PATH_VALUES.get(m.group(1), DEFAULT_PATH_VALUE), path)


# --- tanpa basis data ---------------------------------------------------------------------


def test_every_endpoint_outside_data_is_recorded():
    """Penjaga: endpoint baru di luar /data langsung ketahuan di CI bila belum diputuskan."""
    outside = {
        (rule.method, rule.path)
        for rule in RULES
        if not rule.path.startswith("/api/v1/data/") and rule.kind == "all_of"
    }
    assert outside == set(OTHER_EXPECTED), "endpoint di luar /data wajib dicatat"
    for rule in RULES:
        if (rule.method, rule.path) in OTHER_EXPECTED:
            assert rule.perms == OTHER_EXPECTED[(rule.method, rule.path)], rule


def test_special_rules_point_to_existing_endpoints():
    keys = {(rule.method, rule.path) for rule in RULES}
    assert PUBLIC | LOGIN_ONLY | set(ANY_OF) <= keys


def test_no_endpoint_is_open_by_accident():
    """Selain yang sengaja publik atau cukup login, setiap endpoint butuh minimal satu izin."""
    open_endpoints = [rule for rule in RULES if rule.kind == "all_of" and not rule.perms]
    assert open_endpoints == []


def test_matrix_covers_every_role_and_every_data_endpoint():
    assert set(role_permissions()) == set(ROLES)
    data = {
        (r.method, r.path.removeprefix(DATA_PREFIX))
        for r in RULES
        if r.path.startswith(DATA_PREFIX)
    }
    assert data == set(DATA_EXPECTED)


# --- lewat HTTP ---------------------------------------------------------------------------


@pytest.fixture
def tokens(client, db) -> dict[str, dict]:
    """Satu akun per peran aplikasi (dibuat ulang setiap tes karena app_user dikosongkan)."""
    headers = {}
    for role in ROLES:
        token = make_token(db, f"matriks_{role}", [role])
        headers[role] = {"Authorization": f"Bearer {token}"}
    return headers


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize("rule", RULES, ids=lambda r: f"{r.method} {r.path}")
def test_endpoint_follows_access_matrix(client, db, tokens, rule):
    url = concrete(rule.path)
    body = {} if rule.method in ("POST", "PUT", "PATCH") else None

    def call(headers: dict) -> int:
        kwargs = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        return client.request(rule.method, url, **kwargs).status_code

    anonymous = call({"Authorization": ""})
    if rule.needs_login:
        assert anonymous == 401, f"tanpa login: {anonymous}"
    else:
        assert anonymous not in (401, 403), f"endpoint publik ditolak: {anonymous}"

    mismatches = {}
    for role, granted in role_permissions().items():
        status = call(tokens[role])
        expected_allowed = rule.allows(granted)
        if expected_allowed and status in (401, 403):
            mismatches[role] = f"seharusnya boleh, dapat {status}"
        if not expected_allowed and status != 403:
            mismatches[role] = f"seharusnya 403, dapat {status}"
    assert mismatches == {}
