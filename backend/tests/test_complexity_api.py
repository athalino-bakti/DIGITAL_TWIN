"""DIG-22: endpoint /api/v1/data/complexity-levels terhadap PostgreSQL sungguhan.

Nilai seed tidak di-hardcode di sini karena bisa berubah lewat migrasi (misalnya
penyelarasan dengan dataset dosbim). Setiap tes mengembalikan nilai awal.
"""

import pytest
from sqlalchemy import text

from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

BASE = "/api/v1/data/complexity-levels"
ORDER = ["CX-VH", "CX-H", "CX-M", "CX-L"]


@pytest.fixture
def levels(client, db):
    """Simpan nilai seed sebelum tes dan pulihkan sesudahnya."""
    original = db.execute(
        text("SELECT complexity_id, min_days, max_days, load_weight FROM complexity_levels")
    ).all()
    yield {row.complexity_id: row for row in original}
    for row in original:
        db.execute(
            text(
                "UPDATE complexity_levels SET min_days = :min, max_days = :max,"
                " load_weight = :w WHERE complexity_id = :id"
            ),
            {
                "min": row.min_days,
                "max": row.max_days,
                "w": row.load_weight,
                "id": row.complexity_id,
            },
        )
    db.commit()


def test_list_returns_four_levels_hardest_first(client, levels):
    body = client.get(BASE).json()
    assert [level["complexity_id"] for level in body] == ORDER
    for level in body:
        seed = levels[level["complexity_id"]]
        assert (level["min_days"], level["max_days"], level["load_weight"]) == (
            seed.min_days,
            seed.max_days,
            seed.load_weight,
        )
        assert level["complexity_name"]
        assert level["task_count"] == 0


def test_patch_all_three_values(client, levels):
    response = client.patch(
        f"{BASE}/CX-M", json={"min_days": 2.5, "max_days": 6, "load_weight": 1.1}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["min_days"], body["max_days"], body["load_weight"]) == (2.5, 6.0, 1.1)
    listed = {level["complexity_id"]: level for level in client.get(BASE).json()}
    assert listed["CX-M"]["max_days"] == 6.0


def test_patch_single_value_keeps_others(client, levels):
    seed = levels["CX-L"]
    body = client.patch(f"{BASE}/CX-L", json={"load_weight": 0.75}).json()
    assert (body["min_days"], body["max_days"], body["load_weight"]) == (
        seed.min_days,
        seed.max_days,
        0.75,
    )


def test_min_equal_to_max_is_allowed(client, levels):
    response = client.patch(f"{BASE}/CX-H", json={"min_days": 5, "max_days": 5})
    assert response.status_code == 200


def test_min_greater_than_max_is_422(client, levels):
    response = client.patch(f"{BASE}/CX-H", json={"min_days": 9, "max_days": 4})
    assert response.status_code == 422
    assert error_fields(response) == ["max_days"]


def test_raising_only_min_above_current_max_points_at_min(client, levels):
    above = levels["CX-L"].max_days + 1
    response = client.patch(f"{BASE}/CX-L", json={"min_days": above})
    assert response.status_code == 422
    assert error_fields(response) == ["min_days"]


def test_lowering_only_max_below_current_min_points_at_max(client, levels):
    response = client.patch(f"{BASE}/CX-VH", json={"max_days": levels["CX-VH"].min_days - 1})
    assert response.status_code == 422
    assert error_fields(response) == ["max_days"]


@pytest.mark.parametrize(
    "body",
    [
        {"min_days": -1},
        {"load_weight": -0.1},
        {"max_days": "5"},
        {"load_weight": True},
        {"min_days": None},
        {"complexity_name": "Sedang sekali"},
        {"complexity_id": "CX-X"},
    ],
)
def test_invalid_bodies_are_422(client, levels, body):
    assert client.patch(f"{BASE}/CX-M", json=body).status_code == 422


def test_rejected_patch_changes_nothing(client, levels):
    client.patch(f"{BASE}/CX-M", json={"min_days": 50})
    current = {level["complexity_id"]: level for level in client.get(BASE).json()}
    assert current["CX-M"]["min_days"] == levels["CX-M"].min_days


def test_unknown_level_is_404_and_bad_id_is_422(client, levels):
    assert client.patch(f"{BASE}/CX-XL", json={"load_weight": 1}).status_code == 404
    assert client.patch(f"{BASE}/cx-m", json={"load_weight": 1}).status_code == 422


def test_task_count(client, levels, db):
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
    for number in (1, 2):
        db.execute(
            text(
                "INSERT INTO tasks (task_id, project_id, feature_name, task_name,"
                " required_role_id, complexity_id, priority_rank, estimated_days, phase,"
                " planned_start, planned_finish) VALUES (:id, :pid, 'Login', 'Tabel user',"
                " 'ROLE-DM', 'CX-M', 1, 3, 'dm_dev', '2026-08-24', '2026-08-26')"
            ),
            {"id": f"TSK-000{number}", "pid": project["project_id"]},
        )
    db.commit()
    counts = {level["complexity_id"]: level["task_count"] for level in client.get(BASE).json()}
    assert counts == {"CX-VH": 0, "CX-H": 0, "CX-M": 2, "CX-L": 0}
    assert client.patch(f"{BASE}/CX-M", json={"load_weight": 1}).json()["task_count"] == 2
