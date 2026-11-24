"""DIG-131: entity resolution identitas sumber ke resources lewat resource_alias."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.modules.data.etl.identity import load_alias_index, resolve, resolve_plan_assignments
from app.modules.data.etl.normalize import PlanRow, build_candidates, label_index
from app.modules.data.resource_alias_service import alias_key
from tests.conftest import REQUIRES_DB
from tests.test_resources_api import create as create_member

TRELLO_ID = "5f" + "a" * 22
INDEX = {
    ("project_plan", alias_key("project_plan", "Sari Puspitasari")): "RES-001",
    ("trello", TRELLO_ID): "RES-002",
    ("teamgit", "budi@puti.example"): "RES-003",
}


@pytest.mark.parametrize(
    ("source", "value", "resource_id"),
    [
        ("project_plan", "Sari Puspitasari", "RES-001"),
        ("project_plan", "  sari   PUSPITASARI ", "RES-001"),  # alias_key merapikan spasi dan huruf
        ("trello", TRELLO_ID.upper(), "RES-002"),
        ("teamgit", " Budi@PUTI.example ", "RES-003"),
    ],
)
def test_known_identities_resolve(source, value, resource_id):
    assert resolve(INDEX, source, value) == resource_id


@pytest.mark.parametrize(
    ("source", "value"),
    [
        ("project_plan", "Sari P."),  # varian nama tidak ditebak
        ("project_plan", ""),
        ("trello", "bukan-id-trello"),
        ("trello", "b" * 24),  # id valid tetapi belum dipetakan
        ("teamgit", None),
    ],
)
def test_unknown_identities_are_not_guessed(source, value):
    assert resolve(INDEX, source, value) is None


def plan(pic: str, number: int, code: str) -> PlanRow:
    return PlanRow(
        number,
        "PRJ-001",
        {"task_code": code, "role_label": "ROLE-BE", "pic": pic, "planned_start": "02/11/2026"},
        datetime(2026, 11, 6, tzinfo=UTC),
    )


def test_plan_assignments_get_resource_or_are_reported():
    candidates = build_candidates(
        [plan("Sari Puspitasari", 2, "TSK-0001"), plan("Sari P.", 3, "TSK-0002")],
        {},
        label_index([("ROLE-BE", "Back End Developer")]),
        {},
    )
    before = len(candidates.problems)
    resolved = resolve_plan_assignments(candidates, INDEX)
    mapped, unmapped = resolved.tables["assignments"]
    assert mapped.values["resource_id"] == "RES-001"
    assert unmapped.values["resource_id"] == ""
    (problem,) = resolved.problems[before:]
    assert (problem.row, problem.key, problem.column, problem.value) == (
        3,
        "TSK-0002",
        "resource_id",
        "Sari P.",
    )
    assert "belum dipetakan" in problem.message
    # Kandidat lain tidak berubah.
    assert resolved.tables["tasks"] == candidates.tables["tasks"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_alias_index_is_read_from_the_database(client, db):
    rid = create_member(client)["resource_id"]
    db.execute(text("TRUNCATE resource_alias"))
    db.execute(
        text(
            "INSERT INTO resource_alias (resource_id, source, alias, alias_key) "
            "VALUES (:r, 'project_plan', 'Sari Puspitasari', :k)"
        ),
        {"r": rid, "k": alias_key("project_plan", "Sari Puspitasari")},
    )
    db.commit()
    assert resolve(load_alias_index(db), "project_plan", "SARI puspitasari") == rid
