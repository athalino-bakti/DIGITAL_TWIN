"""DIG-106: ketersediaan (D-09) dan hari libur (D-11) terhadap PostgreSQL sungguhan."""

import pytest
from sqlalchemy import text

from tests.conftest import REQUIRES_DB, error_fields

pytestmark = REQUIRES_DB

AVAILABILITY = "/api/v1/data/availability"
HOLIDAYS = "/api/v1/data/holidays"


@pytest.fixture
def members(client) -> tuple[str, str]:
    ids = []
    for name in ("Sari P.", "Budi"):
        response = client.post(
            "/api/v1/data/resources",
            json={
                "resource_name": name,
                "primary_role_id": "ROLE-BE",
                "join_date": "2024-02-01",
                "seniority": "mid",
            },
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["resource_id"])
    return ids[0], ids[1]


def absence(resource_id: str, **overrides) -> dict:
    return {
        "resource_id": resource_id,
        "date_start": "2026-11-02",
        "date_end": "2026-11-06",
        "absence_type": "planned_leave",
        "is_known_at_planning": True,
    } | overrides


def create(client, resource_id: str, **overrides) -> dict:
    response = client.post(AVAILABILITY, json=absence(resource_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def add_holiday(client, day: str, name: str = "Libur") -> dict:
    response = client.post(HOLIDAYS, json={"holiday_date": day, "holiday_name": name})
    assert response.status_code == 201, response.text
    return response.json()


# --- availability ---


def test_create_assigns_next_id_and_counts_working_days(client, members):
    sari, _ = members
    add_holiday(client, "2026-11-04", "Libur kampus")
    first = create(client, sari)
    assert first == {
        "availability_id": "AVL-001",
        "resource_id": sari,
        "resource_name": "Sari P.",
        "date_start": "2026-11-02",
        "date_end": "2026-11-06",
        "absence_type": "planned_leave",
        "is_known_at_planning": True,
        "calendar_days": 5,
        "working_days": 4,
    }
    second = create(client, sari, date_start="2026-11-09", date_end="2026-11-09")
    assert second["availability_id"] == "AVL-002"


def test_next_id_follows_highest_numeric_id(client, members):
    sari, budi = members
    create(client, sari, availability_id="AVL-041")
    assert create(client, budi)["availability_id"] == "AVL-042"


def test_duplicate_id_is_409(client, members):
    sari, budi = members
    create(client, sari, availability_id="AVL-010")
    response = client.post(AVAILABILITY, json=absence(budi, availability_id="AVL-010"))
    assert response.status_code == 409
    assert error_fields(response) == ["availability_id"]


def test_end_before_start_is_422(client, members):
    response = client.post(
        AVAILABILITY, json=absence(members[0], date_start="2026-11-06", date_end="2026-11-02")
    )
    assert response.status_code == 422
    assert error_fields(response) == ["date_end"]


def test_unknown_resource_is_422(client, members):
    response = client.post(AVAILABILITY, json=absence("RES-999"))
    assert response.status_code == 422
    assert error_fields(response) == ["resource_id"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("date_start", "02/11/2026"),
        ("absence_type", "cuti"),
        ("is_known_at_planning", "ya"),
        ("availability_id", "AVL-1"),
    ],
)
def test_invalid_values_are_422(client, members, field, value):
    response = client.post(AVAILABILITY, json=absence(members[0], **{field: value}))
    assert response.status_code == 422
    assert error_fields(response) == [field]


def test_overlapping_absence_for_same_member_is_409(client, members):
    sari, budi = members
    first = create(client, sari)
    response = client.post(
        AVAILABILITY,
        json=absence(
            sari, date_start="2026-11-06", date_end="2026-11-10", absence_type="sudden_leave"
        ),
    )
    assert response.status_code == 409
    assert error_fields(response) == ["date_start"]
    assert first["availability_id"] in response.json()["detail"]["msg"]
    # Anggota lain di tanggal yang sama tidak bentrok.
    create(client, budi)
    # Bersambung (bukan bertumpuk) boleh.
    create(client, sari, date_start="2026-11-07", date_end="2026-11-08")


def test_rotation_in_may_overlap(client, members):
    sari, _ = members
    create(client, sari)
    create(client, sari, absence_type="rotation_in", is_known_at_planning=False)


def test_list_filters_by_member_and_overlapping_range(client, members):
    sari, budi = members
    october = create(client, sari, date_start="2026-10-28", date_end="2026-11-03")
    november = create(client, budi, date_start="2026-11-20", date_end="2026-11-20")
    december = create(client, sari, date_start="2026-12-01", date_end="2026-12-02")

    def ids(params: dict) -> list[str]:
        return [a["availability_id"] for a in client.get(AVAILABILITY, params=params).json()]

    assert ids({}) == [
        october["availability_id"],
        november["availability_id"],
        december["availability_id"],
    ]
    assert ids({"resource_id": sari}) == [october["availability_id"], december["availability_id"]]
    assert ids({"date_from": "2026-11-01", "date_to": "2026-11-30"}) == [
        october["availability_id"],
        november["availability_id"],
    ]
    assert client.get(AVAILABILITY, params={"resource_id": "bukan"}).status_code == 422


def test_patch_rechecks_rules_and_excludes_itself(client, members):
    sari, budi = members
    item = create(client, sari)
    aid = item["availability_id"]

    response = client.patch(f"{AVAILABILITY}/{aid}", json={"date_end": "2026-11-12"})
    assert response.status_code == 200
    assert response.json()["working_days"] == 9

    response = client.patch(f"{AVAILABILITY}/{aid}", json={"date_end": "2026-11-01"})
    assert response.status_code == 422
    assert error_fields(response) == ["date_end"]

    response = client.patch(f"{AVAILABILITY}/{aid}", json={"absence_type": None})
    assert response.status_code == 422
    assert error_fields(response) == ["absence_type"]

    other = create(client, budi, date_start="2026-11-16", date_end="2026-11-17")
    response = client.patch(
        f"{AVAILABILITY}/{other['availability_id']}", json={"resource_id": sari}
    )
    assert response.status_code == 200
    response = client.patch(
        f"{AVAILABILITY}/{other['availability_id']}", json={"date_start": "2026-11-10"}
    )
    assert response.status_code == 409


def test_delete_and_missing(client, members):
    aid = create(client, members[0])["availability_id"]
    assert client.delete(f"{AVAILABILITY}/{aid}").status_code == 204
    assert client.delete(f"{AVAILABILITY}/{aid}").status_code == 404
    assert client.patch(f"{AVAILABILITY}/AVL-999", json={}).status_code == 404


def test_deleting_member_with_availability_is_409(client, members):
    sari, _ = members
    create(client, sari)
    response = client.delete(f"/api/v1/data/resources/{sari}")
    assert response.status_code == 409


# --- holidays ---


def test_holiday_crud(client):
    christmas = add_holiday(client, "2026-12-25", "Hari Raya Natal")
    assert christmas == {
        "holiday_date": "2026-12-25",
        "holiday_name": "Hari Raya Natal",
        "is_weekend": False,
    }
    response = client.patch(f"{HOLIDAYS}/2026-12-25", json={"holiday_name": "Natal"})
    assert response.json()["holiday_name"] == "Natal"
    assert client.delete(f"{HOLIDAYS}/2026-12-25").status_code == 204
    assert client.delete(f"{HOLIDAYS}/2026-12-25").status_code == 404


def test_duplicate_holiday_date_is_409(client):
    add_holiday(client, "2026-08-17", "Hari Kemerdekaan")
    response = client.post(HOLIDAYS, json={"holiday_date": "2026-08-17", "holiday_name": "Lain"})
    assert response.status_code == 409
    assert error_fields(response) == ["holiday_date"]
    assert "Hari Kemerdekaan" in response.json()["detail"]["msg"]


def test_holiday_on_weekend_is_flagged(client):
    assert add_holiday(client, "2026-11-07")["is_weekend"] is True


def test_list_holidays_sorted_and_filtered_by_year(client):
    add_holiday(client, "2027-01-01", "Tahun Baru")
    add_holiday(client, "2026-12-25", "Natal")
    add_holiday(client, "2026-08-17", "Kemerdekaan")

    def dates(params: dict) -> list[str]:
        return [h["holiday_date"] for h in client.get(HOLIDAYS, params=params).json()]

    assert dates({}) == ["2026-08-17", "2026-12-25", "2027-01-01"]
    assert dates({"year": 2026}) == ["2026-08-17", "2026-12-25"]


@pytest.mark.parametrize(
    "body,field",
    [
        ({"holiday_date": "25-12-2026", "holiday_name": "Natal"}, "holiday_date"),
        ({"holiday_date": "2026-12-25", "holiday_name": "   "}, "holiday_name"),
    ],
)
def test_invalid_holiday_is_422(client, body, field):
    response = client.post(HOLIDAYS, json=body)
    assert response.status_code == 422
    assert error_fields(response) == [field]


@pytest.mark.parametrize("path", ["2026-02-30", "2026-1-01", "kemarin"])
def test_invalid_holiday_path_is_422(client, path):
    assert client.patch(f"{HOLIDAYS}/{path}", json={"holiday_name": "x"}).status_code == 422


def test_holiday_changes_working_days_of_existing_absence(client, members):
    aid = create(client, members[0])["availability_id"]
    add_holiday(client, "2026-11-03")
    listed = client.get(AVAILABILITY).json()
    assert [(a["availability_id"], a["working_days"]) for a in listed] == [(aid, 4)]


def test_holidays_table_is_emptied_between_tests(client, db):
    assert db.scalar(text("SELECT count(*) FROM holidays")) == 0
