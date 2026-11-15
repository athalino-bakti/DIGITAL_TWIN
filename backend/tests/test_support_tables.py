"""DIG-220 dan DIG-221: tabel pendukung DATA_CONTRACT 7.3 terhadap PostgreSQL sungguhan.

Constraint diuji langsung lewat SQL karena endpoint kedua tabel belum ada. Perubahan yang bisa
merusak seed (misalnya menghapus peran) selalu di-rollback.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import REQUIRES_DB
from tests.test_projects_api import create as create_project
from tests.test_resources_api import create as create_member

pytestmark = REQUIRES_DB

RESOURCES = "/api/v1/data/resources"


def add_skill(db, resource_id: str, role_id: str, level: int, assessed: str = "2026-10-01"):
    db.execute(
        text(
            "INSERT INTO resource_skills (resource_id, role_id, proficiency_level, assessed_date) "
            "VALUES (:r, :role, :level, :assessed)"
        ),
        {"r": resource_id, "role": role_id, "level": level, "assessed": assessed},
    )


def constraint_of(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


def violated(db, statement, params=None) -> str | None:
    """Jalankan statement yang diharapkan gagal, kembalikan nama constraint, lalu rollback."""
    with pytest.raises(IntegrityError) as caught:
        db.execute(text(statement), params or {})
        db.flush()
    db.rollback()
    return constraint_of(caught.value)


# --- resource_skills (DIG-220) ---------------------------------------------------------------


def test_skill_levels_one_to_three_are_accepted(client, db):
    rid = create_member(client)["resource_id"]
    for level, role in ((1, "ROLE-QA"), (2, "ROLE-FE"), (3, "ROLE-BE")):
        add_skill(db, rid, role, level)
    db.commit()
    rows = db.execute(
        text("SELECT role_id, proficiency_level FROM resource_skills WHERE resource_id = :r"),
        {"r": rid},
    ).all()
    assert sorted(rows) == [("ROLE-BE", 3), ("ROLE-FE", 2), ("ROLE-QA", 1)]


@pytest.mark.parametrize("level", [0, 4, -1])
def test_skill_level_outside_one_to_three_is_rejected(client, db, level):
    rid = create_member(client)["resource_id"]
    name = violated(
        db,
        "INSERT INTO resource_skills VALUES (:r, 'ROLE-BE', :level, '2026-10-01')",
        {"r": rid, "level": level},
    )
    assert name == "ck_resource_skills_proficiency_level_range"


def test_one_row_per_member_and_role(client, db):
    rid = create_member(client)["resource_id"]
    add_skill(db, rid, "ROLE-BE", 2)
    db.commit()
    name = violated(
        db, "INSERT INTO resource_skills VALUES (:r, 'ROLE-BE', 3, '2026-11-01')", {"r": rid}
    )
    assert name == "pk_resource_skills"


@pytest.mark.parametrize(
    "resource_id,role_id,constraint",
    [
        ("RES-999", "ROLE-BE", "fk_resource_skills_resource_id_resources"),
        (None, "ROLE-XYZ", "fk_resource_skills_role_id_roles"),
    ],
)
def test_unknown_member_or_role_is_rejected(client, db, resource_id, role_id, constraint):
    rid = resource_id or create_member(client)["resource_id"]
    name = violated(
        db,
        "INSERT INTO resource_skills VALUES (:r, :role, 2, '2026-10-01')",
        {"r": rid, "role": role_id},
    )
    assert name == constraint


@pytest.mark.parametrize("column", ["proficiency_level", "assessed_date"])
def test_level_and_assessed_date_are_required(client, db, column):
    rid = create_member(client)["resource_id"]
    values = {"proficiency_level": "2", "assessed_date": "'2026-10-01'"} | {column: "NULL"}
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO resource_skills VALUES "
                f"(:r, 'ROLE-BE', {values['proficiency_level']}, {values['assessed_date']})"
            ),
            {"r": rid},
        )
        db.flush()
    db.rollback()


def test_deleting_member_deletes_its_skills(client, db):
    rid = create_member(client)["resource_id"]
    add_skill(db, rid, "ROLE-BE", 3)
    add_skill(db, rid, "ROLE-QA", 1)
    db.commit()

    assert client.delete(f"{RESOURCES}/{rid}").status_code == 204
    db.expire_all()
    left = db.scalar(
        text("SELECT count(*) FROM resource_skills WHERE resource_id = :r"), {"r": rid}
    )
    assert left == 0


def test_role_used_by_a_skill_cannot_be_deleted(client, db):
    # ROLE-QA hanya dipakai keahlian ini, bukan peran utama anggota mana pun.
    rid = create_member(client, primary_role_id="ROLE-BE")["resource_id"]
    add_skill(db, rid, "ROLE-QA", 2)
    db.commit()
    name = violated(db, "DELETE FROM roles WHERE role_id = 'ROLE-QA'")
    assert name == "fk_resource_skills_role_id_roles"
    assert db.scalar(text("SELECT count(*) FROM roles WHERE role_id = 'ROLE-QA'")) == 1


# --- change_event_details (DIG-221) ----------------------------------------------------------


def add_event(client, db, event_id: str = "EVT-001", event_date: str = "2026-09-01") -> str:
    pid = create_project(client)["project_id"]
    db.execute(
        text(
            "INSERT INTO change_events (event_id, project_id, event_type, event_date) "
            "VALUES (:e, :p, 'change_request', :d)"
        ),
        {"e": event_id, "p": pid, "d": event_date},
    )
    db.commit()
    return event_id


def add_detail(db, event_id: str, approver: str | None = None, approved=None, resolved=None):
    db.execute(
        text(
            "INSERT INTO change_event_details "
            "(event_id, approved_by_resource_id, approved_date, resolved_date) "
            "VALUES (:e, :a, :ad, :rd)"
        ),
        {"e": event_id, "a": approver, "ad": approved, "rd": resolved},
    )


def test_detail_with_only_event_id_is_accepted(client, db):
    eid = add_event(client, db)
    add_detail(db, eid)
    db.commit()
    row = db.execute(text("SELECT * FROM change_event_details WHERE event_id = :e"), {"e": eid})
    assert row.one()[1:] == (None, None, None)


def test_one_detail_per_event(client, db):
    eid = add_event(client, db)
    add_detail(db, eid, resolved="2026-09-05")
    db.commit()
    name = violated(db, "INSERT INTO change_event_details (event_id) VALUES (:e)", {"e": eid})
    assert name == "pk_change_event_details"


@pytest.mark.parametrize(
    "event_id,approver,constraint",
    [
        ("EVT-999", None, "fk_change_event_details_event_id_change_events"),
        (None, "RES-999", "fk_change_event_details_approved_by_resource_id_resources"),
    ],
)
def test_unknown_event_or_approver_is_rejected(client, db, event_id, approver, constraint):
    eid = event_id or add_event(client, db)
    name = violated(
        db,
        "INSERT INTO change_event_details (event_id, approved_by_resource_id) VALUES (:e, :a)",
        {"e": eid, "a": approver},
    )
    assert name == constraint


def test_deleting_event_deletes_its_detail(client, db):
    eid = add_event(client, db)
    add_detail(db, eid, approved="2026-09-02")
    db.commit()
    db.execute(text("DELETE FROM change_events WHERE event_id = :e"), {"e": eid})
    db.commit()
    left = db.scalar(
        text("SELECT count(*) FROM change_event_details WHERE event_id = :e"), {"e": eid}
    )
    assert left == 0


def test_approver_cannot_be_deleted_and_api_says_why(client, db):
    eid = add_event(client, db)
    rid = create_member(client)["resource_id"]
    add_detail(db, eid, approver=rid, approved="2026-09-02")
    db.commit()

    response = client.delete(f"{RESOURCES}/{rid}")
    assert response.status_code == 409
    assert "persetujuan kejadian perubahan" in response.json()["detail"]["msg"]
    db.expire_all()
    approver = db.scalar(
        text("SELECT approved_by_resource_id FROM change_event_details WHERE event_id = :e"),
        {"e": eid},
    )
    assert approver == rid


def test_dates_before_event_date_are_not_blocked_by_the_database(client, db):
    """Aturan tanggal ada di validator (DATA_CONTRACT 7.3), bukan constraint."""
    eid = add_event(client, db, event_date="2026-09-10")
    add_detail(db, eid, approved="2026-09-01", resolved="2026-09-01")
    db.commit()
