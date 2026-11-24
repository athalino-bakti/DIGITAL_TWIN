"""DIG-146: ringkasan kualitas data per impor, baris ditolak, dan unduh CSV."""

import csv
import io

import pytest
from sqlalchemy import text

from app.modules.data.quality.engine import Finding, Report, RuleSummary
from app.modules.data.quality.store import save_report
from tests.conftest import REQUIRES_DB, make_token
from tests.test_quality_staging import CLEAR_JOBS

pytestmark = REQUIRES_DB

URL = "/api/v1/data/quality"


def finding(rule, level, row, column="planned_finish", characteristic="consistency"):
    return Finding(
        rule, characteristic, level, "project_plan", "tasks", row, f"TSK-{row:04d}", column, "x",
        f"{rule} baris {row}",
    )  # fmt: skip


REPORT = Report(
    "project_plan",
    findings=[
        finding("DQ-TSK-009", "tolak", 17),
        finding("DQ-TSK-012", "peringatan", 17, "planned_start"),
        finding("DQ-TSK-012", "peringatan", 23, "planned_start"),
        finding("DQ-TSK-001", "tolak", 5, "task_name", "completeness"),
    ],
    summaries=[
        RuleSummary("DQ-TSK-001", "project_plan", "tasks", "completeness", "tolak", "Wajib", 40, 1),
        RuleSummary("DQ-TSK-009", "project_plan", "tasks", "consistency", "tolak", "Urutan", 40, 1),
        RuleSummary("DQ-TSK-012", "project_plan", "tasks", "consistency", "peringatan", "Libur",
                    40, 2),
    ],
)  # fmt: skip


def add_job(db, source="project_plan", status="succeeded", details=None):
    return db.scalar(
        text(
            "INSERT INTO import_job (source, trigger, status, finished_at, details) "
            "VALUES (:source, 'manual', :status, now(), CAST(:details AS jsonb)) RETURNING job_id"
        ),
        {"source": source, "status": status, "details": details},
    )


@pytest.fixture
def job_id(client, session_factory):
    with session_factory() as db:
        db.execute(text(CLEAR_JOBS))
        add_job(db)  # impor lama tanpa validasi
        job = add_job(
            db, details='{"file_name": "project_plan_PRJ-002.csv", "project_id": "PRJ-002"}'
        )
        save_report(db, job, REPORT)
        db.commit()
    return job


def test_summary_counts_rows_and_characteristics(client, job_id):
    body = client.get(f"{URL}/summary").json()
    assert (body["job_id"], body["file_name"], body["project_id"]) == (
        job_id,
        "project_plan_PRJ-002.csv",
        "PRJ-002",
    )
    assert (body["rows_checked"], body["rows_rejected"], body["rows_with_warning"]) == (40, 2, 1)
    assert body["pass_rate"] == 0.95
    scores = {c["characteristic"]: c for c in body["characteristics"]}
    assert list(scores) == ["completeness", "consistency", "currentness", "traceability"]
    assert (scores["consistency"]["checked"], scores["consistency"]["violated"]) == (80, 3)
    assert scores["traceability"]["pass_rate"] is None
    assert [r["rule_id"] for r in body["rules"]] == ["DQ-TSK-001", "DQ-TSK-009", "DQ-TSK-012"]


def test_rows_checked_counts_same_table_per_source(client, session_factory):
    report = Report(
        "project_plan",
        summaries=[
            RuleSummary("DQ-TSK-001", "project_plan", "tasks", "completeness", "tolak", "x", 40, 0),
            RuleSummary("DQ-TSK-001", "trello", "tasks", "completeness", "tolak", "x", 15, 0),
        ],
    )
    with session_factory() as db:
        db.execute(text(CLEAR_JOBS))
        job = add_job(db)
        save_report(db, job, report)
        db.commit()
    body = client.get(f"{URL}/summary", params={"job_id": job}).json()
    assert body["rows_checked"] == 40 + 15


def test_summary_without_validation_is_empty(client, job_id):
    body = client.get(f"{URL}/summary", params={"source": "trello"}).json()
    assert (body["job_id"], body["rows_checked"], body["pass_rate"]) == (None, 0, None)
    assert client.get(f"{URL}/summary", params={"job_id": 999999}).status_code == 404


def test_rejected_rows_group_findings_per_row(client, job_id):
    body = client.get(f"{URL}/rejected-rows", params={"job_id": job_id}).json()
    assert body["total"] == 3
    assert [(i["row_number"], i["level"]) for i in body["items"]] == [
        (5, "tolak"),
        (17, "tolak"),
        (23, "peringatan"),
    ]
    row17 = body["items"][1]["findings"]
    assert [(f["rule_id"], f["level"]) for f in row17] == [
        ("DQ-TSK-009", "tolak"),
        ("DQ-TSK-012", "peringatan"),
    ]


@pytest.mark.parametrize(
    ("params", "rows"),
    [
        ({"level": "peringatan"}, [23]),
        ({"rule_id": "DQ-TSK-012"}, [17, 23]),
        ({"characteristic": "completeness"}, [5]),
        ({"page": 2, "page_size": 2}, [23]),
    ],
)
def test_rejected_rows_filters_and_pages(client, job_id, params, rows):
    body = client.get(f"{URL}/rejected-rows", params={"job_id": job_id, **params}).json()
    assert [i["row_number"] for i in body["items"]] == rows


def test_csv_downloads(client, job_id):
    response = client.get(f"{URL}/rejected-rows.csv", params={"job_id": job_id})
    assert response.headers["content-type"].startswith("text/csv")
    assert f"baris_ditolak_job_{job_id}.csv" in response.headers["content-disposition"]
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0].startswith("source,table,row_number")
    assert len(lines) == 1 + 4  # satu baris per temuan
    summary = client.get(f"{URL}/summary.csv", params={"job_id": job_id}).content.decode(
        "utf-8-sig"
    )
    assert summary.splitlines()[1] == "DQ-TSK-001,tasks,completeness,tolak,40,1,0.975"


def test_csv_cells_cannot_start_a_formula(client, session_factory):
    values = ['=HYPERLINK("http://x")', "+1", "-2", "@SUM(A1)", "\tTAB", "\rCR"]
    report = Report(
        "project_plan",
        findings=[
            Finding("DQ-TSK-009", "consistency", "tolak", "project_plan", "tasks", 10 + i,
                    value, "planned_finish", value, value)
            for i, value in enumerate(values)
        ],
        summaries=[RuleSummary("=DQ", "project_plan", "tasks", "consistency", "tolak", "x", 40, 6)],
    )  # fmt: skip
    with session_factory() as db:
        db.execute(text(CLEAR_JOBS))
        job = add_job(db)
        save_report(db, job, report)
        db.commit()
    body = client.get(f"{URL}/rejected-rows.csv", params={"job_id": job}).content
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"), newline="")))
    assert [(r["row_key"], r["value"], r["message"]) for r in rows] == [
        ("'" + v, "'" + v, "'" + v) for v in values
    ]
    assert rows[0]["row_number"] == "10"  # angka tidak diberi awalan
    summary = client.get(f"{URL}/summary.csv", params={"job_id": job}).content.decode("utf-8-sig")
    assert summary.splitlines()[1].startswith("'=DQ,tasks,")


@pytest.mark.parametrize(("role", "code"), [("system_analyst", 200), ("anggota_tim", 403)])
def test_quality_report_needs_data_quality_permission(client, session_factory, role, code):
    with session_factory() as db:
        token = make_token(db, f"mutu-{role}", [role])
    response = client.get(f"{URL}/summary", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == code
