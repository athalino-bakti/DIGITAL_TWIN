"""DIG-222: tabel audit_log, helper record_audit, dan GET /api/v1/data/audit-log."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.modules.auth.models import AppUser
from app.modules.data.audit import record_audit, to_json
from app.modules.data.audit_models import AuditLog
from app.modules.data.enums import TaskStatus
from tests.conftest import REQUIRES_DB, make_token

URL = "/api/v1/data/audit-log"


# --- tanpa basis data -------------------------------------------------------------------


def test_values_become_json():
    assert to_json(date(2026, 11, 25)) == "2026-11-25"
    assert to_json(Decimal("2.5")) == 2.5
    assert to_json(TaskStatus.DONE) == "done"
    assert to_json(None) is None


class FakeSession:
    def __init__(self):
        self.added = []

    def add(self, entry):
        self.added.append(entry)


def test_update_keeps_only_changed_columns():
    db = FakeSession()
    entry = record_audit(
        db,
        action="update",
        entity="tasks",
        entity_id="TSK-0001",
        source="etl",
        before={"status": "in_progress", "planned_finish": date(2026, 11, 30), "phase": "be"},
        after={"status": "done", "planned_finish": date(2026, 11, 30), "phase": "be"},
    )
    assert (entry.before, entry.after) == ({"status": "in_progress"}, {"status": "done"})
    assert (entry.actor_user_id, entry.actor_label) == (None, "sistem")
    assert db.added == [entry]


def test_update_without_change_writes_nothing():
    db = FakeSession()
    same = {"status": "done"}
    assert record_audit(
        db, action="update", entity="tasks", entity_id="TSK-0001", source="etl",
        before=same, after=dict(same),
    ) is None  # fmt: skip
    assert db.added == []


def test_actor_is_snapshotted():
    actor = AppUser(user_id=7, username="sari")
    entry = record_audit(
        FakeSession(), action="insert", entity="holidays", entity_id="2026-12-25",
        source="form", actor=actor, after={"holiday_name": "Natal"},
    )  # fmt: skip
    assert (entry.actor_user_id, entry.actor_label) == (7, "sari")


@pytest.mark.parametrize(("field", "value"), [("action", "ubah"), ("source", "excel")])
def test_unknown_action_or_source_is_rejected(field, value):
    kwargs = {"action": "insert", "source": "form", field: value}
    with pytest.raises(ValueError):
        record_audit(FakeSession(), entity="tasks", entity_id="TSK-0001", **kwargs)


# --- dengan basis data -------------------------------------------------------------------


def add_job(db) -> int:
    return db.scalar(
        text(
            "INSERT INTO import_job (source, trigger, status, finished_at) "
            "VALUES ('project_plan', 'manual', 'succeeded', now()) RETURNING job_id"
        )
    )


@pytest.fixture
def empty(client, db):
    db.execute(text("TRUNCATE audit_log RESTART IDENTITY"))
    db.commit()
    yield
    db.execute(text("TRUNCATE audit_log RESTART IDENTITY"))
    db.commit()


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_saved_entry_and_set_null_on_delete(empty, db):
    job = add_job(db)
    user = AppUser(username="pengubah", full_name="Pengubah", password_hash="x")
    db.add(user)
    db.flush()
    record_audit(
        db, action="update", entity="tasks", entity_id="TSK-0001", source="etl",
        actor=user, import_job_id=job, before={"status": "in_progress"}, after={"status": "done"},
    )  # fmt: skip
    db.commit()
    db.execute(text("DELETE FROM import_job WHERE job_id = :j"), {"j": job})
    db.execute(text("DELETE FROM app_user WHERE user_id = :u"), {"u": user.user_id})
    db.commit()
    db.expire_all()
    entry = db.scalar(select(AuditLog))
    assert entry.occurred_at is not None
    # Job dan akun dihapus: jejak tetap ada, label pengubah tetap terbaca.
    assert (entry.import_job_id, entry.actor_user_id, entry.actor_label) == (None, None, "pengubah")
    assert entry.after == {"status": "done"}


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize(
    ("action", "before", "after"),
    [
        ("insert", '{"a": 1}', '{"a": 2}'),
        ("delete", '{"a": 1}', '{"a": 2}'),
        ("update", None, '{"a": 2}'),
        ("hapus", None, None),
    ],
)
def test_values_must_match_action(empty, db, action, before, after):
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO audit_log (actor_label, action, entity, entity_id, source, before, "
                "after) VALUES ('sistem', :a, 'tasks', 'TSK-0001', 'etl', "
                "CAST(:b AS jsonb), CAST(:f AS jsonb))"
            ),
            {"a": action, "b": before, "f": after},
        )
    db.rollback()


@REQUIRES_DB[0]
@REQUIRES_DB[1]
def test_read_endpoint_filters_and_pages(empty, client, db):
    job = add_job(db)
    for number in range(3):
        record_audit(
            db, action="insert", entity="tasks", entity_id=f"TSK-000{number}", source="etl",
            import_job_id=job, after={"task_name": f"Task {number}"},
        )  # fmt: skip
    record_audit(
        db, action="insert", entity="holidays", entity_id="2026-12-25", source="form",
        after={"holiday_name": "Natal"},
    )  # fmt: skip
    db.commit()

    body = client.get(URL, params={"entity": "tasks", "page_size": 2}).json()
    assert (body["total"], len(body["items"])) == (3, 2)
    assert body["items"][0]["entity_id"] == "TSK-0002"  # terbaru dulu
    assert client.get(URL, params={"import_job_id": job}).json()["total"] == 3
    one = client.get(URL, params={"entity": "holidays", "entity_id": "2026-12-25"}).json()
    assert one["items"][0]["after"] == {"holiday_name": "Natal"}
    assert client.get(URL, params={"page_size": 201}).status_code == 422


@REQUIRES_DB[0]
@REQUIRES_DB[1]
@pytest.mark.parametrize(
    ("role", "code"), [("system_analyst", 200), ("admin_data", 200), ("anggota_tim", 403)]
)
def test_read_endpoint_needs_data_quality_read(client, db, role, code):
    token = make_token(db, f"audit-{role}", [role])
    response = client.get(URL, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == code
