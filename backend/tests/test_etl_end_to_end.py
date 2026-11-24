"""DIG-135: ETL end-to-end dengan data sintetis kotor (seed 42, as-of 2026-11-06).

Alur: berkas mentah kotor (`synthetic.dirty.write_dirty`) diimpor ke staging seperti unggahan
Project Plan dan impor Trello, lalu ETL memvalidasi dan memuatnya ke tabel final. Kunci jawaban
cacat ada di `manifest_cacat.csv`.
"""

import csv
import json
from datetime import date

import pytest
from sqlalchemy import func, insert, select, text, update

from app.db.base import Base
from app.integrations.project_plan.parser import parse_project_plan, read_table
from app.integrations.trello.parser import parse_board_export
from app.modules.data.audit_models import AuditLog
from app.modules.data.etl.load import run
from app.modules.data.import_job_models import ImportJob
from app.modules.data.models import Assignment, Task, TaskDependency
from app.modules.data.project_plan_staging import save_project_plan
from app.modules.data.resource_alias_service import alias_key
from app.modules.data.staging_models import TrelloListMapping
from app.modules.data.trello_staging import save_trello_import
from synthetic.dirty import write_dirty
from synthetic.final_sources import final_source_rows
from synthetic.world import build_world
from tests.conftest import REQUIRES_DB

pytestmark = REQUIRES_DB

SEED, AS_OF = 42, date(2026, 11, 6)
LIST_STATUS = {
    "Backlog": "not_started",
    "To Do": "not_started",
    "In Progress": "in_progress",
    "Blocked": "blocked",
    "Hold": "on_hold",
    "QA": "in_qa",
    "Done": "done",
}
REFERENCE = ("holidays", "projects", "resources")


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


@pytest.fixture(scope="module")
def dirty(tmp_path_factory):
    world = build_world(SEED, AS_OF)
    out = tmp_path_factory.mktemp("dirty")
    write_dirty(world, out)
    with (out / "manifest_cacat.csv").open(encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle))
    return world, out, manifest


@pytest.fixture
def loaded(client, db, dirty):
    world, out, manifest = dirty
    db.execute(text("TRUNCATE audit_log, resource_alias, staging_trello_action RESTART IDENTITY"))
    db.execute(text("TRUNCATE trello_list_mapping, import_job CASCADE"))
    db.commit()

    # Rujukan final sources (D-01 s.d. D-03, D-11) dari dunia sintetis yang sama.
    rows = final_source_rows(world)
    tables = Base.metadata.tables
    for name in REFERENCE:
        db.execute(insert(tables[name]), rows[name])

    # Alias identitas: PIC Project Plan dan id member Trello.
    board = json.loads((out / "raw" / "trello" / "trello_board.json").read_text(encoding="utf-8"))
    member_id = {m["username"]: m["id"] for m in board["members"]}
    for resource in world.resources:
        pic = resource.aliases["project_plan_pic"]
        aliases = [("project_plan", pic, alias_key("project_plan", pic))]
        trello = member_id.get(resource.aliases["trello_username"])
        if trello:
            aliases.append(("trello", trello, trello))
        for source, alias, key in aliases:
            db.execute(
                text(
                    "INSERT INTO resource_alias (resource_id, source, alias, alias_key) "
                    "VALUES (:r, :s, :a, :k)"
                ),
                {"r": resource.resource_id, "s": source, "a": alias, "k": key},
            )

    # Staging Trello dan pemetaan list ke status.
    save_trello_import(db, parse_board_export(board), None)
    for name, status in LIST_STATUS.items():
        db.execute(
            update(TrelloListMapping)
            .where(TrelloListMapping.list_name == name)
            .values(status=status)
        )

    # Staging Project Plan: satu job sukses per berkas, seperti unggahan DIG-25.
    plans = sorted((out / "raw" / "project_plan").glob("project_plan_*.csv"))
    for path in plans:
        project_id = path.stem.removeprefix("project_plan_")
        job = ImportJob(source="project_plan", trigger="manual", status="succeeded",
                        finished_at=func.now())  # fmt: skip
        db.add(job)
        db.flush()
        parsed = parse_project_plan(read_table(path.read_bytes(), path.name))
        assert not parsed.errors, parsed.errors
        save_project_plan(db, parsed, job.job_id, project_id, path.name)
    db.commit()

    reports = run(db)
    db.commit()
    return {"manifest": manifest, "reports": reports, "plans": len(plans)}


def plan_defects(manifest, kind):
    return [
        row["lokasi"].removeprefix("Kode=") for row in manifest
        if row["sumber"] == "project_plan" and row["jenis"] == kind
    ]  # fmt: skip


def test_final_rows_equal_rows_that_passed_validation(db, loaded):
    reports = loaded["reports"]
    assert len(reports) == loaded["plans"]
    loaded_tasks = sum(r.inserted["tasks"] for r in reports)
    assert loaded_tasks > 0
    assert count(db, Task) == loaded_tasks
    for report in reports:
        # Setiap baris kandidat dimuat atau ditolak; tidak ada yang hilang diam-diam.
        assert report.inserted["tasks"] + report.rejected["tasks"] == report.plan_rows
    assert count(db, TaskDependency) == sum(r.inserted["task_dependencies"] for r in reports)
    assert count(db, Assignment) == sum(r.inserted["assignments"] for r in reports)
    assert count(db, TaskDependency) > 0 and count(db, Assignment) > 0


def test_duplicated_plan_row_is_loaded_once(db, loaded):
    codes = plan_defects(loaded["manifest"], "duplikat")
    assert codes
    # Salinan ganda ditolak, baris aslinya tetap dimuat satu kali.
    assert sorted(db.scalars(select(Task.task_id).where(Task.task_id.in_(codes)))) == sorted(
        set(codes)
    )


@pytest.mark.parametrize("kind", ["format_tanggal", "wajib_kosong"])
def test_dirty_project_plan_rows_are_not_loaded(db, loaded, kind):
    codes = plan_defects(loaded["manifest"], kind)
    assert codes, f"manifest tanpa cacat {kind}"
    present = set(db.scalars(select(Task.task_id).where(Task.task_id.in_(codes))))
    assert present == set()


def test_dependency_cycle_is_not_loaded(db, loaded):
    (cycle,) = [
        r for r in loaded["manifest"]
        if r["sumber"] == "project_plan" and r["jenis"] == "siklus_dependency"
    ]  # fmt: skip
    first = cycle["lokasi"].removeprefix("Kode=")
    later = cycle["nilai_kotor"].removeprefix(cycle["nilai_asli"]).strip("; ").split(" ")[0]
    pairs = set(
        db.execute(select(TaskDependency.task_id, TaskDependency.depends_on_task_id)).tuples()
    )
    # Validator (DIG-142) menolak edge penutup siklus; kedua arah tidak boleh sama-sama dimuat.
    assert not {(first, later), (later, first)} <= pairs
    assert sum(r.rejected["task_dependencies"] for r in loaded["reports"]) >= 1


def test_reported_identities_are_really_unmapped(db, loaded):
    from app.modules.data.etl.identity import load_alias_index, resolve

    index = load_alias_index(db)
    reported = [
        p for r in loaded["reports"] for p in r.problems if p["column"] == "resource_id"
    ]  # fmt: skip
    for problem in reported:
        assert resolve(index, problem["source"], problem["value"]) is None


def test_every_change_is_audited_with_its_job(db, loaded):
    inserted = sum(sum(r.inserted.values()) for r in loaded["reports"])
    assert count(db, AuditLog) == inserted
    jobs = set(db.scalars(select(AuditLog.import_job_id)))
    assert jobs == {r.job_id for r in loaded["reports"] if r.inserted}


def test_running_twice_changes_nothing(db, loaded):
    before = (
        count(db, Task),
        count(db, TaskDependency),
        count(db, Assignment),
        count(db, AuditLog),
    )
    again = run(db)
    db.commit()
    assert all(not r.inserted and not r.updated for r in again)
    after = (count(db, Task), count(db, TaskDependency), count(db, Assignment), count(db, AuditLog))
    assert after == before
