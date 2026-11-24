"""DIG-145: hasil validator disimpan ke data_quality_result dan rejected_row per import_job."""

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.modules.data.quality.engine import Finding, Report, RuleSummary
from app.modules.data.quality.store import save_report
from app.modules.data.quality_models import DataQualityResult, RejectedRow
from tests.conftest import REQUIRES_DB
from tests.test_quality_staging import CLEAR_JOBS

pytestmark = REQUIRES_DB


def report() -> Report:
    return Report(
        "trello",
        findings=[
            Finding("DQ-TRL-001", "completeness", "peringatan", "trello", "staging_trello_action",
                    None, "c" * 24, "card_name", "Analisis", "Kartu tanpa kode task"),
            Finding("DQ-TSK-009", "consistency", "tolak", "trello", "tasks",
                    17, "TSK-0016", "planned_finish", "2026-11-02", "Urutan tanggal salah"),
        ],
        summaries=[
            RuleSummary("DQ-TRL-001", "trello", "staging_trello_action", "completeness",
                        "peringatan", "Kartu memuat kode task", 5, 1),
            RuleSummary("DQ-TSK-009", "trello", "tasks", "consistency", "tolak",
                        "Urutan tanggal", 20, 1),
        ],
    )  # fmt: skip


@pytest.fixture
def job_id(db):
    db.execute(text(CLEAR_JOBS))
    job = db.scalar(
        text(
            "INSERT INTO import_job (source, trigger, status, finished_at) "
            "VALUES ('trello', 'manual', 'succeeded', now()) RETURNING job_id"
        )
    )
    db.commit()
    return job


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_report_is_saved_per_rule_and_per_finding(db, job_id):
    assert save_report(db, job_id, report()) == (2, 2)
    db.commit()

    rule = db.scalar(select(DataQualityResult).where(DataQualityResult.rule_id == "DQ-TSK-009"))
    assert (rule.job_id, rule.table_name, rule.checked, rule.violated) == (job_id, "tasks", 20, 1)
    levels = {r.level: r for r in db.scalars(select(RejectedRow))}
    assert set(levels) == {"tolak", "peringatan"}
    assert (levels["tolak"].row_number, levels["tolak"].column_name) == (17, "planned_finish")
    assert levels["peringatan"].row_number is None


def test_duplicate_rule_per_source_is_summed(db, job_id):
    doubled = report()
    doubled.summaries.append(
        RuleSummary("DQ-TSK-009", "trello", "tasks", "consistency", "tolak", "Urutan", 10, 2)
    )
    assert save_report(db, job_id, doubled) == (2, 2)
    db.commit()
    rule = db.scalar(select(DataQualityResult).where(DataQualityResult.rule_id == "DQ-TSK-009"))
    assert (rule.checked, rule.violated) == (30, 3)


def test_saving_again_replaces_previous_result(db, job_id):
    save_report(db, job_id, report())
    db.commit()
    save_report(db, job_id, Report("trello"))
    db.commit()
    assert (count(db, DataQualityResult), count(db, RejectedRow)) == (0, 0)


def test_deleting_job_deletes_its_result(db, job_id):
    save_report(db, job_id, report())
    db.commit()
    db.execute(text("DELETE FROM import_job WHERE job_id = :id"), {"id": job_id})
    db.commit()
    assert (count(db, DataQualityResult), count(db, RejectedRow)) == (0, 0)


@pytest.mark.parametrize(
    "column, value",
    [("level", "info"), ("characteristic", "accuracy"), ("violated", 99)],
)
def test_invalid_result_is_rejected(db, job_id, column, value):
    row = {
        "job_id": job_id,
        "source": "trello",
        "rule_id": "DQ-X",
        "table_name": "tasks",
        "characteristic": "consistency",
        "level": "tolak",
        "rule_text": "x",
        "checked": 5,
        "violated": 1,
    } | {column: value}
    db.add(DataQualityResult(**row))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
