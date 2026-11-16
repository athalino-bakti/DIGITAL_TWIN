"""DIG-208: header keamanan di setiap respons API, termasuk error dan preflight CORS."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

EXPECTED = {
    "cache-control": "no-store",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


@pytest.fixture
def raw_client():
    # Tanpa login dan tanpa basis data: cukup untuk melihat header.
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize(
    ("method", "path", "status"),
    [
        ("GET", "/api/v1/health", 200),
        ("GET", "/api/v1/data/projects", 401),
        ("GET", "/api/v1/tidak-ada", 404),
        ("POST", "/api/v1/auth/login", 422),
    ],
)
def test_api_responses_carry_security_headers(raw_client, method, path, status):
    response = raw_client.request(method, path, json={})
    assert response.status_code == status
    for name, value in EXPECTED.items():
        assert response.headers[name] == value, name


def test_cors_preflight_carries_security_headers(raw_client):
    response = raw_client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_docs_page_is_not_blocked_by_api_csp(raw_client):
    response = raw_client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


def test_headers_are_not_duplicated(raw_client):
    response = raw_client.get("/api/v1/health")
    names = [name.lower() for name, _ in response.headers.multi_items()]
    for name in EXPECTED:
        assert names.count(name) == 1, name
