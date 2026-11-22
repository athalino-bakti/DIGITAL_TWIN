"""DIG-116: endpoint unggah Project Plan (DIG-114) dan staging_project_plan (DIG-113) terhadap
PostgreSQL sungguhan. Fixture dari generator data sintetis J&C (seed 42, as-of 2026-11-06)."""

import pytest
from sqlalchemy import text

from app.modules.data import project_plan_router
from tests.conftest import REQUIRES_DB
from tests.test_project_plan_parser import CLEAN, DEFECTS, DIRTY, xlsx_from_csv

pytestmark = REQUIRES_DB

URL = "/api/v1/data/imports/project-plan"
CSV = "text/csv"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def jobs(db):
    db.execute(text("TRUNCATE import_job CASCADE"))
    db.commit()
    return db


def upload(client, data: bytes, name: str = DIRTY.name, mime: str = CSV, **form):
    form = {
        key: str(value).lower() if isinstance(value, bool) else value for key, value in form.items()
    }
    return client.post(URL, files={"file": (name, data, mime)}, data=form)


def job_rows(db) -> list:
    return db.execute(
        text("SELECT job_id, source, status, rows_read, rows_written, triggered_by FROM import_job")
    ).all()


def staged(db) -> dict[str, list]:
    rows: dict[str, list] = {}
    for row in db.execute(
        text("SELECT * FROM staging_project_plan ORDER BY row_number")
    ).mappings():
        rows.setdefault(row["task_code"], []).append(row)
    return rows


def test_preview_maps_columns_without_creating_a_job(client, jobs):
    response = upload(client, DIRTY.read_bytes())
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["dry_run"], body["applied"], body["job_id"]) == (True, False, None)
    assert (body["project_id"], body["project_id_source"]) == ("PRJ-002", "file_name")
    assert (body["file_type"], body["delimiter"], body["total_rows"]) == ("csv", ",", 11)
    assert body["mapping"]["Kode"] == "task_code"
    assert body["unmapped_headers"] == ["No"]
    assert body["errors"] == [] and body["missing_required"] == []
    first = body["preview_rows"][0]
    assert (first["row"], first["values"]["task_code"]) == (2, "TSK-0041")
    assert len(body["preview_rows"]) == 11
    assert len(body["file_sha256"]) == 64 and body["same_file_job_id"] is None
    assert job_rows(jobs) == []
    assert jobs.scalar(text("SELECT count(*) FROM staging_project_plan")) == 0


def test_import_records_one_job_and_stores_values_unchanged(client, jobs):
    response = upload(client, DIRTY.read_bytes(), dry_run=False)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["applied"], body["job_status"], body["rows_read"], body["rows_written"]) == (
        True,
        "succeeded",
        11,
        11,
    )
    [job] = job_rows(jobs)
    assert job == (body["job_id"], "project_plan", "succeeded", 11, 11, "penguji")

    rows = staged(jobs)
    assert {r["import_job_id"] for found in rows.values() for r in found} == {job.job_id}
    assert {r["project_id"] for found in rows.values() for r in found} == {"PRJ-002"}
    for code, attribute, value in DEFECTS:
        assert rows[code][0][attribute] == value, (code, attribute)
    assert [r["row_number"] for r in rows["TSK-0046"]] == [4, 11]  # duplikat tetap dua baris
    assert rows["TSK-0041"][0]["raw"]["No"] == "1"
    assert rows["TSK-0041"][0]["file_name"] == DIRTY.name

    details = jobs.scalar(text("SELECT details FROM import_job"))
    assert details["project_id"] == "PRJ-002"
    assert details["file_sha256"] == body["file_sha256"]


def test_uploading_the_same_file_again_warns_and_makes_a_new_batch(client, jobs):
    first = upload(client, DIRTY.read_bytes(), dry_run=False).json()
    preview = upload(client, DIRTY.read_bytes()).json()
    assert preview["same_file_job_id"] == first["job_id"]
    assert upload(client, CLEAN.read_bytes(), name=DIRTY.name).json()["same_file_job_id"] is None

    second = upload(client, DIRTY.read_bytes(), dry_run=False).json()
    assert second["job_id"] != first["job_id"]
    counts = jobs.execute(
        text("SELECT import_job_id, count(*) FROM staging_project_plan GROUP BY 1 ORDER BY 1")
    ).all()
    assert counts == [(first["job_id"], 11), (second["job_id"], 11)]


def test_project_id_parameter_wins_over_the_file_name(client, jobs):
    body = upload(client, CLEAN.read_bytes(), project_id="PRJ-005").json()
    assert (body["project_id"], body["project_id_source"]) == ("PRJ-005", "parameter")


@pytest.mark.parametrize(
    ("name", "form", "field"),
    [
        ("plan.csv", {}, "project_id"),
        (CLEAN.name, {"project_id": "PRJ-5"}, "project_id"),
        ("project_plan_PRJ-002.txt", {}, "file"),
        (CLEAN.name, {"column_map": "[1, 2]"}, "column_map"),
        (CLEAN.name, {"column_map": "{bukan json"}, "column_map"),
    ],
)
def test_invalid_requests_are_rejected_without_a_job(client, jobs, name, form, field):
    response = upload(client, CLEAN.read_bytes(), name=name, dry_run=False, **form)
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert job_rows(jobs) == []


def test_file_too_large_is_rejected_without_a_job(client, jobs, monkeypatch):
    monkeypatch.setattr(project_plan_router, "MAX_BYTES", 100)
    response = upload(client, CLEAN.read_bytes(), dry_run=False)
    assert response.status_code == 413
    assert job_rows(jobs) == []


def test_broken_file_is_a_failed_job(client, jobs):
    broken = b"No,Fitur,Catatan\n1,Presensi,-\n"
    preview = upload(client, broken)
    assert preview.status_code == 200
    assert "Kolom wajib tidak ditemukan" in preview.json()["errors"][0]["message"]
    assert job_rows(jobs) == []

    response = upload(client, broken, dry_run=False)
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    [job] = job_rows(jobs)
    assert (detail["job_id"], job.status, job.source) == (job.job_id, "failed", "project_plan")
    assert "Kolom wajib tidak ditemukan" in detail["error"]
    assert jobs.scalar(text("SELECT count(*) FROM staging_project_plan")) == 0

    empty = upload(client, b"", dry_run=False)
    assert empty.status_code == 422
    assert "Berkas kosong" in empty.json()["detail"]["error"]


def test_another_running_import_is_a_conflict(client, jobs):
    jobs.execute(
        text(
            "INSERT INTO import_job (source, trigger, status) "
            "VALUES ('project_plan', 'manual', 'running')"
        )
    )
    jobs.commit()
    response = upload(client, CLEAN.read_bytes(), dry_run=False)
    assert response.status_code == 409, response.text
    assert jobs.scalar(text("SELECT count(*) FROM staging_project_plan")) == 0


def test_xlsx_upload_with_explicit_mapping(client, jobs):
    response = upload(
        client,
        xlsx_from_csv(CLEAN),
        name="project_plan_PRJ-002.xlsx",
        mime=XLSX,
        dry_run=False,
        sheet="Plan",
        column_map='{"Catatan": null}',
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["file_type"], body["sheet_name"], body["sheets"]) == (
        "xlsx",
        "Plan",
        ["Plan", "Catatan"],
    )
    assert body["typed_cells"]["Mulai Rencana"] == 10
    assert "Catatan" in body["unmapped_headers"]
    row = staged(jobs)["TSK-0041"][0]
    assert (row["sheet_name"], row["planned_start"], row["notes"]) == ("Plan", "2026-09-02", None)
