"""DIG-143 dan DIG-144: currentness per sumber (DQ-CUR-001), kartu Trello tanpa kode
(DQ-TRL-001), dan CLI validator."""

import csv
from datetime import date

import pytest
from sqlalchemy import text

from app.modules.data.quality import run
from app.modules.data.quality.currentness import currentness_report, measure
from app.modules.data.quality.engine import SourceRow
from app.modules.data.quality.staging import read_trello_cards, validate_trello
from tests.conftest import REQUIRES_DB
from tests.test_quality_rules import CLEAN
from tests.test_quality_sources import write_csv


def requires_db(test):
    for mark in REQUIRES_DB:
        test = mark(test)
    return test


def card(name: str) -> SourceRow:
    return SourceRow(None, "c" * 24, {"card_id": "c" * 24, "card_name": name, "board_id": "b" * 24})


# --- DQ-TRL-001 ------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Analisis kebutuhan presensi", "tsk-0041 | huruf kecil", ""])
def test_DQ_TRL_001_card_without_code_is_a_warning(name):
    [finding] = validate_trello([card(name)]).findings
    assert (finding.rule_id, finding.level, finding.characteristic) == (
        "DQ-TRL-001",
        "peringatan",
        "completeness",
    )


@pytest.mark.parametrize("name", ["TSK-0041 | Analisis presensi", "WLI-0003 | Reset sandi"])
def test_DQ_TRL_001_card_with_task_or_workload_code_passes(name):
    assert validate_trello([card(name)]).findings == []


ACTION = (
    "INSERT INTO staging_trello_action (action_id, action_type, action_date, board_id, card_id, "
    "card_name, raw) VALUES (:id, 'updateCard', :at, :board, :card, :name, '{}')"
)


@requires_db
def test_trello_cards_use_the_latest_card_name(db):
    db.execute(text("TRUNCATE staging_trello_action, staging_project_plan, audit_log, import_job"))
    board, first, second = "b" * 24, "1" * 24, "2" * 24
    for action_id, at, card_id, name in [
        ("a" * 24, "2026-10-01T09:00:00+07:00", first, "Analisis presensi"),
        ("d" * 24, "2026-10-02T09:00:00+07:00", first, "TSK-0041 | Analisis presensi"),
        ("e" * 24, "2026-10-03T09:00:00+07:00", second, "Rapat koordinasi"),
    ]:
        db.execute(
            text(ACTION), {"id": action_id, "at": at, "board": board, "card": card_id, "name": name}
        )
    db.commit()
    cards = read_trello_cards(db)
    assert [(c.key, c.values["card_name"]) for c in cards] == [
        (first, "TSK-0041 | Analisis presensi"),
        (second, "Rapat koordinasi"),
    ]
    assert [f.row_key for f in validate_trello(cards).findings] == [second]


# --- DQ-CUR-001 ------------------------------------------------------------------------------

JOB = (
    "INSERT INTO import_job (source, trigger, status, started_at, finished_at) "
    "VALUES (:source, 'schedule', :status, :at, :at)"
)


@requires_db
def test_DQ_CUR_001_currentness_per_source(db):
    db.execute(text("TRUNCATE staging_trello_action, staging_project_plan, audit_log, import_job"))
    for source, status, at in [
        ("trello", "succeeded", "2026-11-01T02:00:00+07:00"),
        ("trello", "failed", "2026-11-05T02:00:00+07:00"),  # gagal: tidak dihitung
        ("trello", "succeeded", "2026-11-09T02:00:00+07:00"),  # sesudah as_of: diabaikan
        ("project_plan", "succeeded", "2026-10-20T10:00:00+07:00"),
    ]:
        db.execute(text(JOB), {"source": source, "status": status, "at": at})
    db.execute(
        text(ACTION),
        {
            "id": "a" * 24,
            "at": "2026-10-30T16:00:00+07:00",
            "board": "b" * 24,
            "card": "c" * 24,
            "name": "TSK-0001 | A",
        },
    )
    db.commit()

    rows = {row["source"]: row for row in measure(db, date(2026, 11, 6))}
    assert rows["trello"]["import_age_days"] == 5
    assert (rows["trello"]["source_lag_days"], rows["trello"]["data_age_days"]) == (2, 7)
    assert rows["project_plan"]["import_age_days"] == 17
    assert rows["project_plan"]["newest_source_at"] is None  # Project Plan tanpa cap waktu sumber
    assert rows["teamgit"]["last_success_at"] is None

    report = currentness_report(db, date(2026, 11, 6))
    assert {(f.rule_id, f.row_key, f.level) for f in report.findings} == {
        ("DQ-CUR-001", "project_plan", "peringatan"),
        ("DQ-CUR-001", "teamgit", "peringatan"),
    }
    [summary] = report.summaries
    assert (summary.checked, summary.violated) == (3, 2)


@requires_db
def test_DQ_CUR_001_recent_imports_pass(db):
    db.execute(text("TRUNCATE staging_trello_action, staging_project_plan, audit_log, import_job"))
    for source in ("trello", "project_plan", "teamgit"):
        db.execute(
            text(JOB), {"source": source, "status": "succeeded", "at": "2026-11-06T08:00:00+07:00"}
        )
    db.commit()
    assert currentness_report(db, date(2026, 11, 6)).findings == []


# --- CLI -------------------------------------------------------------------------------------


def test_cli_writes_findings_summary_and_completeness(tmp_path, capsys):
    folder, out = tmp_path / "csv", tmp_path / "hasil"
    folder.mkdir()
    for table, rows in CLEAN.items():
        write_csv(folder, table, rows)
    write_csv(folder, "tasks", [*CLEAN["tasks"], {**CLEAN["tasks"][0], "status": "selesai"}])

    assert run.main(["--final-sources", str(folder), "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "DQ-TSK-003" in printed and "DQ-TSK-005" in printed
    with (out / "temuan.csv").open(encoding="utf-8") as handle:
        findings = list(csv.DictReader(handle))
    assert {row["rule_id"] for row in findings} == {"DQ-TSK-003", "DQ-TSK-005"}
    with (out / "baris_ditolak.csv").open(encoding="utf-8") as handle:
        [rejected] = list(csv.DictReader(handle))
    assert (rejected["row_number"], rejected["rule_ids"]) == ("4", "DQ-TSK-003;DQ-TSK-005")
    assert (out / "ringkasan.csv").exists() and (out / "kelengkapan.csv").exists()


def test_cli_needs_a_target():
    with pytest.raises(SystemExit):
        run.main([])
