"""DIG-96 (story DIG-19): skenario akses data pribadi per peran aplikasi.

Kriteria penerimaan DIG-19:
1. Heatmap seluruh anggota dan D-09 availability hanya untuk Kaur/Asman dan System Analyst.
2. Anggota tim hanya melihat task dan beban miliknya.
3. Alamat surel commit tidak pernah ditampilkan.
"""

import re
from datetime import date

import pytest
from sqlalchemy import select, text, update

from app.core.privacy import alias_ref, mask_email, mask_emails_deep, mask_emails_in_text
from app.modules.auth.models import AppUser
from app.modules.data import resource_alias_service
from app.modules.data.audit import record_audit
from app.modules.data.enums import IdentitySource
from app.modules.data.models import Assignment, Availability, Task, WorkloadItem
from app.modules.data.resource_alias_models import ResourceAlias
from tests.conftest import REQUIRES_DB, make_token
from tests.test_heatmap_api import assign, member, project, task

DATA = "/api/v1/data"
HEATMAP = "/api/v1/digital-twin/workload-heatmap"
HEATMAP_PARAMS = {"start": "2026-03-02", "weeks": 1, "as_of": "2026-03-04"}
EMAIL = "sari.puspitasari@puti.ac.id"
EMAIL_SHOWN = re.compile(r"[A-Za-z0-9._%+-]{2,}@")  # dua huruf atau lebih sebelum @


# --- penyamaran (tanpa basis data) ----------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("sari.puspitasari@puti.ac.id", "s***@puti.ac.id"),
        ("  B@x.example ", "B***@x.example"),
        ("116237328+dev@users.noreply.github.com", "1***@users.noreply.github.com"),
        ("bukan-email", "***"),
        ("@tanpa-lokal.id", "***"),
    ],
)
def test_mask_email(raw, masked):
    assert mask_email(raw) == masked


def test_mask_emails_in_text_and_nested_json():
    assert mask_emails_in_text(f"commit oleh {EMAIL} dan b@x.io") == (
        "commit oleh s***@puti.ac.id dan b***@x.io"
    )
    nested = {"alias": EMAIL, "riwayat": [{"oleh": EMAIL}, 3, None], "jumlah": 2}
    assert mask_emails_deep(nested) == {
        "alias": "s***@puti.ac.id",
        "riwayat": [{"oleh": "s***@puti.ac.id"}, 3, None],
        "jumlah": 2,
    }


def test_alias_ref_is_stable_and_does_not_contain_the_email():
    ref = alias_ref("teamgit", EMAIL)
    assert re.fullmatch(r"ref-[0-9a-f]{32}", ref)
    assert ref == alias_ref("teamgit", EMAIL)
    assert ref != alias_ref("teamgit", "lain@puti.ac.id")
    assert ref != alias_ref("trello", EMAIL)
    assert "sari" not in ref


# --- data uji dengan basis data -------------------------------------------------------------


@pytest.fixture
def team(client, db) -> dict:
    """Dua anggota dengan task, beban non-proyek, dan ketidakhadiran masing-masing."""
    sikep = project(client, "SIKEP", 1)
    sari, budi = member(client, "Sari"), member(client, "Budi")
    db.add_all([task("TSK-0001", sikep, "CX-M"), task("TSK-0002", sikep, "CX-M")])
    db.flush()
    db.add_all(
        [
            assign(1, "TSK-0001", sari),
            assign(2, "TSK-0002", budi),
            WorkloadItem(
                item_id="WLI-0001",
                resource_id=budi,
                item_type="ticket",
                severity="high",
                received_date=date(2026, 3, 2),
            ),
            Availability(
                availability_id="AVL-001",
                resource_id=budi,
                date_start=date(2026, 3, 5),
                date_end=date(2026, 3, 5),
                absence_type="sudden_leave",
            ),
        ]
    )
    db.commit()
    return {"sari": sari, "budi": budi}


def login(db, username: str, roles: list[str], resource_id: str | None = None) -> dict:
    token = make_token(db, username, roles)
    if resource_id is not None:
        db.execute(
            update(AppUser).where(AppUser.username == username).values(resource_id=resource_id)
        )
        db.commit()
    return {"Authorization": f"Bearer {token}"}


ROLES = ["kaur_asman", "system_analyst", "anggota_tim", "admin_data", "admin_it"]
PERSONAL = ["/availability", "/workload-items", "/change-events"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize("role", ROLES)
@pytest.mark.parametrize("path", PERSONAL)
def test_personal_data_only_for_kaur_and_system_analyst(client, db, team, role, path):
    headers = login(db, f"u-{role}", [role], team["sari"])
    response = client.get(f"{DATA}{path}", headers=headers)
    expected = 200 if role in {"kaur_asman", "system_analyst"} else 403
    assert response.status_code == expected, response.text


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize("role", ["kaur_asman", "system_analyst"])
def test_full_heatmap_for_kaur_and_system_analyst(client, db, team, role):
    headers = login(db, f"u-{role}", [role])
    body = client.get(HEATMAP, params=HEATMAP_PARAMS, headers=headers).json()
    assert {row["resource_id"] for row in body["rows"]} == {team["sari"], team["budi"]}


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_member_heatmap_shows_only_own_row_even_when_filtering_others(client, db, team):
    headers = login(db, "sari", ["anggota_tim"], team["sari"])
    params = HEATMAP_PARAMS | {"resource_id": team["budi"]}
    body = client.get(HEATMAP, params=params, headers=headers).json()
    assert [row["resource_id"] for row in body["rows"]] == [team["sari"]]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize("role", ["admin_data", "admin_it"])
def test_heatmap_closed_for_roles_without_workload_permission(client, db, team, role):
    headers = login(db, f"u-{role}", [role])
    assert client.get(HEATMAP, params=HEATMAP_PARAMS, headers=headers).status_code == 403


# --- task milik sendiri (DIG-94) --------------------------------------------------------------


def task_ids(client, headers) -> list[str]:
    response = client.get(f"{DATA}/tasks", headers=headers)
    assert response.status_code == 200, response.text
    return [item["task_id"] for item in response.json()]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_member_sees_only_own_tasks(client, db, team):
    sari = login(db, "sari", ["anggota_tim"], team["sari"])
    assert task_ids(client, sari) == ["TSK-0001"]
    assert client.get(f"{DATA}/tasks/TSK-0001", headers=sari).status_code == 200
    # Task anggota lain dilaporkan tidak ada, supaya keberadaannya pun tidak bocor.
    assert client.get(f"{DATA}/tasks/TSK-0002", headers=sari).status_code == 404


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_member_keeps_released_task_but_not_others(client, db, team):
    db.execute(update(Assignment).values(released_date=date(2026, 3, 3)))
    db.execute(update(Task).where(Task.task_id == "TSK-0001").values(status="done"))
    db.commit()
    assert task_ids(client, login(db, "sari", ["anggota_tim"], team["sari"])) == ["TSK-0001"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_unlinked_member_sees_no_tasks(client, db, team):
    headers = login(db, "tanpa-tautan", ["anggota_tim"])
    assert task_ids(client, headers) == []
    assert client.get(f"{DATA}/tasks/TSK-0001", headers=headers).status_code == 404


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize("role", ["kaur_asman", "system_analyst", "admin_data"])
def test_coordinators_and_data_admin_see_all_tasks(client, db, team, role):
    headers = login(db, f"u-{role}", [role], team["sari"])
    assert task_ids(client, headers) == ["TSK-0001", "TSK-0002"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_member_with_second_role_follows_the_wider_role(client, db, team):
    headers = login(db, "sari-sa", ["anggota_tim", "system_analyst"], team["sari"])
    assert task_ids(client, headers) == ["TSK-0001", "TSK-0002"]


# --- email commit tidak pernah ditampilkan (DIG-95) --------------------------------------------

ALIASES = f"{DATA}/resource-aliases"


def assert_no_email(payload) -> None:
    assert not EMAIL_SHOWN.search(str(payload)), payload


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_teamgit_alias_is_masked_in_every_response_but_stored_intact(client, db, team):
    created = client.post(
        ALIASES, json={"resource_id": team["sari"], "source": "teamgit", "alias": EMAIL}
    )
    assert created.status_code == 201, created.text
    assert (created.json()["alias"], created.json()["alias_key"]) == ("s***@puti.ac.id",) * 2
    alias_id = created.json()["alias_id"]
    patched = client.patch(f"{ALIASES}/{alias_id}", json={"display_name": "Sari P"})
    for body in (created.json(), patched.json(), client.get(ALIASES).json()):
        assert_no_email(body)
    stored = db.scalar(select(ResourceAlias.alias).where(ResourceAlias.alias_id == alias_id))
    assert stored == EMAIL  # pencocokan identitas tetap memakai nilai asli


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_trello_alias_is_not_masked(client, team):
    member_id = "c15c71bfe2f234308c072307"
    created = client.post(
        ALIASES, json={"resource_id": team["sari"], "source": "trello", "alias": member_id}
    )
    assert created.json()["alias"] == member_id


@pytest.fixture
def teamgit_staging(monkeypatch):
    """Kolektor teamgit sementara; staging commit sungguhan menyusul di DIG-27."""
    seen = date(2026, 3, 2)
    sightings = [(EMAIL, None, "Sari P", seen), ("Budi@PUTI.ac.id", None, "Budi", seen)]
    monkeypatch.setitem(
        resource_alias_service.COLLECTORS, IdentitySource.TEAMGIT, lambda db: iter(sightings)
    )


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_unmapped_teamgit_is_masked_and_mapped_through_alias_ref(client, db, team, teamgit_staging):
    listed = client.get(f"{ALIASES}/unmapped", params={"source": "teamgit"}).json()
    assert_no_email(listed)
    sari = next(item for item in listed if item["display_name"] == "Sari P")
    assert sari["alias"] == "s***@puti.ac.id"
    assert sari["alias_key"] == sari["alias_ref"]

    created = client.post(
        ALIASES,
        json={
            "resource_id": team["sari"],
            "source": "teamgit",
            "alias": sari["alias"],  # bentuk tersamar dari daftar, diabaikan server
            "alias_ref": sari["alias_ref"],
        },
    )
    assert created.status_code == 201, created.text
    assert_no_email(created.json())
    stored = db.scalar(select(ResourceAlias).where(ResourceAlias.source == "teamgit"))
    assert (stored.alias, stored.alias_key) == (EMAIL, EMAIL)
    remaining = client.get(f"{ALIASES}/unmapped", params={"source": "teamgit"}).json()
    assert [item["display_name"] for item in remaining] == ["Budi"]


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize("ref", [alias_ref("teamgit", "tidak.ada@puti.ac.id"), "ref-" + "0" * 32])
def test_unknown_alias_ref_is_rejected(client, team, teamgit_staging, ref):
    response = client.post(
        ALIASES,
        json={"resource_id": team["sari"], "source": "teamgit", "alias": "x", "alias_ref": ref},
    )
    assert response.status_code == 422
    assert "alias_ref" in response.text


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_audit_log_masks_emails(client, db):
    db.execute(text("TRUNCATE audit_log RESTART IDENTITY"))
    record_audit(
        db, action="insert", entity="resource_alias", entity_id=f"teamgit:{EMAIL}",
        source="form", after={"alias": EMAIL, "resource_id": "RES-001"},
        note=f"dipetakan dari commit {EMAIL}",
    )  # fmt: skip
    db.commit()
    body = client.get(f"{DATA}/audit-log").json()
    assert_no_email(body)
    item = body["items"][0]
    assert item["after"] == {"alias": "s***@puti.ac.id", "resource_id": "RES-001"}
    assert item["entity_id"] == "teamgit:s***@puti.ac.id"
    db.execute(text("TRUNCATE audit_log RESTART IDENTITY"))
    db.commit()
