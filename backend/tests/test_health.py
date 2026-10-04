from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_liveness_does_not_need_database(client):
    def forbidden_database():
        raise AssertionError("Liveness tidak boleh mengakses database")

    app.dependency_overrides[get_db] = forbidden_database
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_readiness_checks_connection(client):
    session = Mock()
    app.dependency_overrides[get_db] = lambda: session
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "connected"}
    session.execute.assert_called_once()
    assert str(session.execute.call_args.args[0]) == "SELECT 1"


def test_database_failure_returns_503_without_exposing_details(client):
    session = Mock()
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("secret"))
    app.dependency_overrides[get_db] = lambda: session
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database belum tersedia"}


def test_local_frontend_cors(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_route_returns_404(client):
    assert client.get("/api/v1/missing").status_code == 404
