"""DIG-220 dan DIG-221: tabel pendukung DATA_CONTRACT 7.3 terhadap PostgreSQL sungguhan.

Constraint diuji langsung lewat SQL karena endpoint kedua tabel belum ada. Perubahan yang bisa
merusak seed (misalnya menghapus peran) selalu di-rollback.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.conftest import REQUIRES_DB
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
