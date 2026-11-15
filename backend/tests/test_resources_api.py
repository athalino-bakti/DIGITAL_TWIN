"""DIG-100, DIG-101, DIG-103: anggota (D-02) dan peran (D-03) terhadap PostgreSQL sungguhan."""

from datetime import date, timedelta

import pytest
from sqlalchemy import text

from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

RESOURCES = "/api/v1/data/resources"
ROLES = "/api/v1/data/roles"


def member(**overrides) -> dict:
    return {
        "resource_name": "Sari P.",
        "primary_role_id": "ROLE-BE",
        "join_date": "2024-02-01",
        "seniority": "mid",
    } | overrides


def create(client, **overrides) -> dict:
    response = client.post(RESOURCES, json=member(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def roles(client, db):
    """Simpan nilai peran sebelum tes dan pulihkan sesudahnya."""
    original = db.execute(text("SELECT role_id, capacity_reference, description FROM roles")).all()
    yield {row.role_id: row for row in original}
    for row in original:
        db.execute(
            text("UPDATE roles SET capacity_reference = :c, description = :d WHERE role_id = :id"),
            {"c": row.capacity_reference, "d": row.description, "id": row.role_id},
        )
    db.commit()


# --- CRUD anggota (DIG-100) ---


def test_create_assigns_next_id_and_stores_secondary_roles_with_semicolons(client, db):
    first = create(client, secondary_role_ids=["ROLE-DM", "ROLE-FE"])
    second = create(client, resource_name="Budi")
    assert (first["resource_id"], second["resource_id"]) == ("RES-001", "RES-002")
    assert first["secondary_role_ids"] == ["ROLE-DM", "ROLE-FE"]
    assert second["secondary_role_ids"] == []
    stored = db.execute(
        text("SELECT resource_id, secondary_role_ids FROM resources ORDER BY resource_id")
    ).all()
    assert [tuple(row) for row in stored] == [("RES-001", "ROLE-DM;ROLE-FE"), ("RES-002", None)]


def test_next_id_follows_highest_existing_id(client):
    create(client, resource_id="RES-041")
    assert create(client, resource_name="Budi")["resource_id"] == "RES-042"


def test_duplicate_resource_id_is_409(client):
    create(client, resource_id="RES-010")
    response = client.post(RESOURCES, json=member(resource_id="RES-010"))
    assert response.status_code == 409
    assert error_fields(response) == ["resource_id"]


def test_list_get_patch_delete(client):
    created = create(client)
    rid = created["resource_id"]
    assert [r["resource_id"] for r in client.get(RESOURCES).json()] == [rid]
    assert client.get(f"{RESOURCES}/{rid}").json() == created

    response = client.patch(
        f"{RESOURCES}/{rid}", json={"seniority": "senior", "cross_role_capable": True}
    )
    assert response.status_code == 200
    assert response.json() == created | {"seniority": "senior", "cross_role_capable": True}

    assert client.delete(f"{RESOURCES}/{rid}").status_code == 204
    assert client.get(f"{RESOURCES}/{rid}").status_code == 404
    assert client.get(f"{RESOURCES}/bukan-id").status_code == 422


def test_patch_secondary_roles_replaces_and_clears(client, db):
    rid = create(client, secondary_role_ids=["ROLE-DM"])["resource_id"]
    body = client.patch(f"{RESOURCES}/{rid}", json={"secondary_role_ids": ["ROLE-QA", "ROLE-TW"]})
    assert body.json()["secondary_role_ids"] == ["ROLE-QA", "ROLE-TW"]
    body = client.patch(f"{RESOURCES}/{rid}", json={"secondary_role_ids": []})
    assert body.json()["secondary_role_ids"] == []
    stored = db.scalar(
        text("SELECT secondary_role_ids FROM resources WHERE resource_id = :id"), {"id": rid}
    )
    assert stored is None


def test_patch_required_field_to_null_is_422(client):
    rid = create(client)["resource_id"]
    response = client.patch(f"{RESOURCES}/{rid}", json={"join_date": None})
    assert response.status_code == 422
    assert error_fields(response) == ["join_date"]


def test_delete_resource_with_assignment_is_409(client, db):
    rid = create(client)["resource_id"]
    project = client.post(
        "/api/v1/data/projects",
        json={
            "project_name": "LMS",
            "process_owner": "Akademik",
            "priority_rank": 1,
            "start_date": "2026-08-24",
            "target_launch_date": "2026-12-09",
        },
    ).json()
    db.execute(
        text(
            "INSERT INTO tasks (task_id, project_id, feature_name, task_name, required_role_id,"
            " complexity_id, priority_rank, estimated_days, phase, planned_start, planned_finish)"
            " VALUES ('TSK-0001', :pid, 'Login', 'API login', 'ROLE-BE', 'CX-M', 1, 3, 'be_dev',"
            " '2026-08-24', '2026-08-26')"
        ),
        {"pid": project["project_id"]},
    )
    db.execute(
        text(
            "INSERT INTO assignments (assignment_id, task_id, resource_id, role_in_task,"
            " assigned_date) VALUES ('ASG-0001', 'TSK-0001', :rid, 'ROLE-BE', '2026-08-24')"
        ),
        {"rid": rid},
    )
    db.commit()
    response = client.delete(f"{RESOURCES}/{rid}")
    assert response.status_code == 409
    assert client.get(f"{RESOURCES}/{rid}").status_code == 200


# --- Validasi FK peran (DIG-103) ---


def test_unknown_primary_role_is_422(client):
    response = client.post(RESOURCES, json=member(primary_role_id="ROLE-PM"))
    assert response.status_code == 422
    assert error_fields(response) == ["primary_role_id"]


def test_unknown_secondary_role_is_422(client):
    response = client.post(RESOURCES, json=member(secondary_role_ids=["ROLE-DM", "ROLE-XYZ"]))
    assert response.status_code == 422
    assert error_fields(response) == ["secondary_role_ids"]
    assert "ROLE-XYZ" in response.json()["detail"][0]["msg"]


def test_primary_role_cannot_also_be_secondary(client):
    response = client.post(RESOURCES, json=member(secondary_role_ids=["ROLE-BE"]))
    assert response.status_code == 422
    assert error_fields(response) == ["secondary_role_ids"]


def test_changing_primary_to_an_existing_secondary_is_422(client):
    rid = create(client, secondary_role_ids=["ROLE-DM"])["resource_id"]
    response = client.patch(f"{RESOURCES}/{rid}", json={"primary_role_id": "ROLE-DM"})
    assert response.status_code == 422
    response = client.patch(
        f"{RESOURCES}/{rid}", json={"primary_role_id": "ROLE-DM", "secondary_role_ids": ["ROLE-BE"]}
    )
    assert response.status_code == 200
    assert response.json()["secondary_role_ids"] == ["ROLE-BE"]


def test_duplicate_secondary_roles_is_422(client):
    response = client.post(RESOURCES, json=member(secondary_role_ids=["ROLE-DM", "ROLE-DM"]))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "secondary",
    ["ROLE-DM;ROLE-FE", ["role-dm"], ["ROLE-DM;ROLE-FE"], ["ROLE DM"]],
)
def test_secondary_roles_must_be_a_list_of_role_ids(client, secondary):
    assert client.post(RESOURCES, json=member(secondary_role_ids=secondary)).status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [{"seniority": "lead"}, {"join_date": "01/02/2024"}, {"resource_name": " "}, {"budget": 1}],
)
def test_invalid_member_fields_are_422(client, overrides):
    assert client.post(RESOURCES, json=member(**overrides)).status_code == 422


# --- Masa onboarding ---


def test_onboarding_flag_follows_join_date(client):
    recent = create(client, join_date=(date.today() - timedelta(days=30)).isoformat())
    veteran = create(client, resource_name="Budi", join_date="2022-01-16")
    assert (recent["tenure_days"], recent["is_onboarding"]) == (30, True)
    assert veteran["is_onboarding"] is False


# --- Peran (DIG-101) ---


def test_list_roles_with_member_counts(client, roles):
    create(client)
    create(client, resource_name="Budi")
    listed = {role["role_id"]: role for role in client.get(ROLES).json()}
    assert set(listed) == set(roles)
    assert listed["ROLE-BE"]["resource_count"] == 2
    assert listed["ROLE-QA"]["resource_count"] == 0


def test_patch_role_capacity_and_description(client, roles):
    response = client.patch(
        f"{ROLES}/ROLE-QA", json={"capacity_reference": 2.5, "description": "  Menguji fitur.  "}
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["capacity_reference"], body["description"]) == (2.5, "Menguji fitur.")
    assert body["role_name"]


def test_empty_description_is_stored_as_null(client, roles):
    assert client.patch(f"{ROLES}/ROLE-QA", json={"description": ""}).json()["description"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"capacity_reference": 0},
        {"capacity_reference": -1},
        {"capacity_reference": "3"},
        {"capacity_reference": None},
        {"role_name": "Penguji"},
    ],
)
def test_invalid_role_updates_are_422(client, roles, body):
    assert client.patch(f"{ROLES}/ROLE-QA", json=body).status_code == 422


def test_unknown_role_is_404(client, roles):
    assert client.patch(f"{ROLES}/ROLE-PM", json={"capacity_reference": 3}).status_code == 404
