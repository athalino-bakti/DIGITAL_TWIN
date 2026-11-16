"""DIG-110 dan DIG-111: tabel resource_alias, endpoint alias, dan daftar identitas belum
terpetakan, terhadap PostgreSQL sungguhan.

Data uji berasal dari generator data sintetis J&C (seed 42, as-of 2026-11-06) dan fixture kecil
hasil pangkasannya. `identity_rows` (kunci jawaban generator) hanya dipakai di tes ini untuk
memeriksa hasil pemetaan, bukan sebagai seed.
"""

import copy
import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import insert, text

from app.db.base import Base
from app.integrations.trello.parser import parse_board_export
from app.modules.data.trello_staging import save_trello_import
from synthetic.final_sources import final_source_rows
from synthetic.raw_sources import identity_rows, trello_board
from synthetic.world import build_world
from tests.conftest import REQUIRES_DB, error_fields
from tests.test_resources_api import create as create_member
from tests.test_support_tables import violated

pytestmark = REQUIRES_DB

URL = "/api/v1/data/resource-aliases"
UNMAPPED = f"{URL}/unmapped"
FIXTURE = Path(__file__).parent / "fixtures" / "trello_board_kecil.json"
TWIN = "f" * 24  # akun Trello kedua milik anggota yang sama (cacat alias_berbeda)

# Identitas di action fixture kecil: pelaku dan anggota yang ditambah atau dilepas.
FIXTURE_IDENTITIES = {
    "c15c71bfe2f234308c072307": 11,
    "0fb87e07f120986b2fc6499d": 3,
    "10439bde607e2b462e8d0bb3": 2,
    "d9d2f5ed0ec69d372d1aa9ea": 1,
    "fa6b594e98e335286308b85b": 1,
    "999999999999999999999999": 1,  # pelaku yang tidak ada di daftar members papan
}


def board_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def load_board(db, board: dict) -> None:
    db.execute(text("TRUNCATE staging_trello_action, trello_list_mapping"))
    save_trello_import(db, parse_board_export(board))
    db.commit()


def add_alias(client, resource_id: str, alias: str, source: str = "trello", **extra) -> dict:
    response = client.post(
        URL, json={"resource_id": resource_id, "source": source, "alias": alias, **extra}
    )
    assert response.status_code == 201, response.text
    return response.json()


def unmapped(client, source: str | None = "trello") -> dict[str, dict]:
    response = client.get(UNMAPPED, params={"source": source} if source else None)
    assert response.status_code == 200, response.text
    return {item["alias_key"]: item for item in response.json()}


# --- tabel dan constraint (DIG-110) ----------------------------------------------------------


def insert_alias(source: str, alias_key: str, resource_id: str) -> str:
    return (
        "INSERT INTO resource_alias (resource_id, source, alias, alias_key) "
        f"VALUES ('{resource_id}', '{source}', '{alias_key}', '{alias_key}')"
    )


def test_same_alias_in_same_source_points_to_one_member(client, db):
    first = create_member(client)["resource_id"]
    second = create_member(client)["resource_id"]
    db.execute(text(insert_alias("teamgit", "sari@j-c.example", first)))
    db.commit()
    assert (
        violated(db, insert_alias("teamgit", "sari@j-c.example", second))
        == "uq_resource_alias_source_alias_key"
    )
    # Kunci yang sama di sumber lain dan alias kedua untuk anggota yang sama tetap boleh.
    db.execute(text(insert_alias("project_plan", "sari@j-c.example", second)))
    db.execute(text(insert_alias("teamgit", "sari.p@j-c.example", first)))
    db.commit()


@pytest.mark.parametrize(
    ("source", "key", "constraint"),
    [
        ("jira", "sari", "ck_resource_alias_source_valid"),
        ("trello", "saripusp", "ck_resource_alias_trello_id_format"),
        ("trello", "F" * 24, "ck_resource_alias_trello_id_format"),
        ("project_plan", "", "ck_resource_alias_alias_key_not_empty"),
    ],
)
def test_invalid_alias_rows_are_rejected(client, db, source, key, constraint):
    rid = create_member(client)["resource_id"]
    assert violated(db, insert_alias(source, key, rid)) == constraint


def test_alias_needs_a_known_member(client, db):
    assert (
        violated(db, insert_alias("teamgit", "x@j-c.example", "RES-999"))
        == "fk_resource_alias_resource_id_resources"
    )


def test_aliases_are_deleted_with_their_member(client, db):
    rid = create_member(client)["resource_id"]
    add_alias(client, rid, "sari@j-c.example", source="teamgit")
    assert client.delete(f"/api/v1/data/resources/{rid}").status_code == 204
    assert client.get(URL).json() == []


# --- CRUD (DIG-111) --------------------------------------------------------------------------


def test_create_normalizes_and_records_who_mapped(client, db):
    rid = create_member(client)["resource_id"]
    created = add_alias(
        client,
        rid,
        "  C15C71BFE2F234308C072307 ",
        username="hendrawira",
        display_name="Hendra Wiratama",
    )
    assert created["alias"] == "C15C71BFE2F234308C072307"
    assert created["alias_key"] == "c15c71bfe2f234308c072307"
    assert created["username"] == "hendrawira"
    user = db.execute(text("SELECT user_id FROM app_user WHERE username = 'penguji'")).scalar()
    assert created["mapped_by_user_id"] == user

    listed = client.get(URL, params={"resource_id": rid, "source": "trello"}).json()
    assert [a["alias_id"] for a in listed] == [created["alias_id"]]
    assert client.get(URL, params={"source": "teamgit"}).json() == []


def test_same_alias_twice_is_a_conflict(client):
    first = create_member(client)["resource_id"]
    second = create_member(client)["resource_id"]
    add_alias(client, first, "Sari.Puspitasari@J-C.example", source="teamgit")
    response = client.post(
        URL,
        json={"resource_id": second, "source": "teamgit", "alias": " sari.puspitasari@j-c.EXAMPLE"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["loc"] == ["body", "alias"]
    assert first in response.json()["detail"]["msg"]


def test_unknown_member_and_bad_trello_id_are_validation_errors(client):
    response = client.post(
        URL, json={"resource_id": "RES-999", "source": "teamgit", "alias": "x@y"}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "resource_not_found"

    rid = create_member(client)["resource_id"]
    response = client.post(URL, json={"resource_id": rid, "source": "trello", "alias": "saripusp"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "alias_format"
    assert error_fields(response) == ["alias"]


def test_update_moves_alias_to_another_member(client):
    first = create_member(client)["resource_id"]
    second = create_member(client)["resource_id"]
    alias = add_alias(client, first, TWIN, username="saripusp2")
    response = client.patch(
        f"{URL}/{alias['alias_id']}", json={"resource_id": second, "display_name": "Sari"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["resource_id"], body["display_name"], body["username"]) == (
        second,
        "Sari",
        "saripusp2",
    )
    assert body["updated_at"] >= alias["updated_at"]

    unknown = client.patch(f"{URL}/{alias['alias_id']}", json={"resource_id": "RES-999"})
    assert unknown.status_code == 422
    # Sumber dan alias tidak bisa diubah lewat PATCH.
    assert client.patch(f"{URL}/{alias['alias_id']}", json={"alias": "x"}).status_code == 422


def test_missing_alias_is_not_found(client):
    assert client.patch(f"{URL}/999999", json={"display_name": "x"}).status_code == 404
    assert client.delete(f"{URL}/999999").status_code == 404


# --- daftar identitas belum terpetakan (DIG-111) ---------------------------------------------


def test_every_trello_identity_starts_unmapped(client, db):
    load_board(db, board_fixture())
    found = unmapped(client)
    assert {key: item["occurrences"] for key, item in found.items()} == FIXTURE_IDENTITIES
    hendra = found["c15c71bfe2f234308c072307"]
    assert (hendra["source"], hendra["username"], hendra["display_name"]) == (
        "trello",
        "hendrawira",
        "Hendra Wiratama",
    )
    assert list(found)[0] == "c15c71bfe2f234308c072307"  # kemunculan terbanyak lebih dulu
    assert hendra["last_seen"].startswith("2026-")
    # Sumber yang belum punya staging (DIG-113, DIG-121) belum punya identitas.
    assert unmapped(client, "teamgit") == {}
    assert unmapped(client, None).keys() == found.keys()


def test_mapping_removes_identity_from_the_list(client, db):
    load_board(db, board_fixture())
    rid = create_member(client)["resource_id"]
    alias = add_alias(client, rid, "C15C71BFE2F234308C072307")
    assert "c15c71bfe2f234308c072307" not in unmapped(client)
    assert len(unmapped(client)) == len(FIXTURE_IDENTITIES) - 1

    assert client.delete(f"{URL}/{alias['alias_id']}").status_code == 204
    assert "c15c71bfe2f234308c072307" in unmapped(client)


def test_second_trello_account_stays_unmapped_until_mapped_manually(client, db):
    """Di fixture dan data generator, akun kedua hanya ada di `idMembers` kartu tanpa action,
    sehingga tidak masuk staging. Di sini ia diberi satu action supaya terlihat."""
    board = board_fixture()
    action = copy.deepcopy(
        next(a for a in board["actions"] if isinstance(a, dict) and a["type"] == "addMemberToCard")
    )
    action.update(id="a" * 24, idMemberCreator=TWIN)
    board["actions"].append(action)
    load_board(db, board)

    owner = create_member(client)["resource_id"]
    original = next(m["id"] for m in board["members"] if m["username"] == "saripusp")
    add_alias(client, owner, original)  # akun asli saja yang dipetakan
    assert TWIN in unmapped(client)
    assert unmapped(client)[TWIN]["username"] == "saripusp2"

    add_alias(client, owner, TWIN, username="saripusp2")
    assert TWIN not in unmapped(client)


def test_generator_identities_all_map_back_to_their_members(client, db):
    """Kunci jawaban generator: setelah semua akun Trello dipetakan, daftar kosong dan setiap
    alias menunjuk anggota yang benar. Alias Project Plan dan TeamGit ikut dibuat lewat API."""
    world = build_world(42, date(2026, 11, 6))
    db.execute(insert(Base.metadata.tables["resources"]), final_source_rows(world)["resources"])
    db.commit()
    board = trello_board(world)
    load_board(db, board)
    member_id = {m["username"]: m["id"] for m in board["members"]}

    header, *rows = identity_rows(world)
    col = {name: i for i, name in enumerate(header)}
    assert len(unmapped(client)) == len(rows)
    for row in rows:
        rid = row[col["resource_id"]]
        username = row[col["trello_username"]]
        add_alias(
            client,
            rid,
            member_id[username],
            username=username,
            display_name=row[col["trello_fullname"]],
        )
        add_alias(client, rid, row[col["project_plan_pic"]], source="project_plan")
        add_alias(
            client,
            rid,
            row[col["git_email"]],
            source="teamgit",
            display_name=row[col["git_author"]],
        )

    assert unmapped(client, None) == {}
    trello = {
        a["alias_key"]: a["resource_id"]
        for a in client.get(URL, params={"source": "trello"}).json()
    }
    assert trello == {
        member_id[row[col["trello_username"]]]: row[col["resource_id"]] for row in rows
    }
    assert len(client.get(URL).json()) == 3 * len(rows)
