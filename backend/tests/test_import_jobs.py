"""DIG-127 s.d. DIG-129: runner job impor, tabel import_job, dan endpoint pemantauan.

Memakai PostgreSQL sungguhan (TEST_DATABASE_URL), karena aturan satu job berjalan per sumber
dan penutupan job macet bergantung pada index unik parsial dan waktu server.
"""

import json
import logging
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.integrations.trello.client import TrelloAuthError, TrelloClient, TrelloRateLimitError
from app.integrations.trello.config import TrelloSettings
from app.modules.data.import_job_models import ImportJob
from app.pipeline.config import PipelineSettings
from app.pipeline.jobs import JobOutcome, import_trello
from app.pipeline.runner import JobAlreadyRunning, run_job
from tests.conftest import REQUIRES_DB, make_token

pytestmark = REQUIRES_DB

FIXTURE = Path(__file__).parent / "fixtures" / "trello_board_kecil.json"
SECRET = "token-rahasia-uji-0123456789"


@pytest.fixture
def jobs_db(session_factory):
    with session_factory() as session:
        session.execute(text("TRUNCATE import_job, staging_trello_action, trello_list_mapping"))
        session.commit()
    return session_factory


def pipeline(**kwargs) -> PipelineSettings:
    values = {"trello_board_ids": "AbCd1234", "import_retry_delay_seconds": 5} | kwargs
    return PipelineSettings(_env_file=None, **values)


class Recorder:
    """Pengganti sleep dan notifier yang mencatat panggilan."""

    def __init__(self):
        self.sleeps: list[float] = []
        self.messages: list[str] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def notify(self, settings, message: str) -> bool:
        self.messages.append(message)
        return True


def scripted(*steps):
    """Job palsu: setiap langkah berupa exception (dilempar) atau JobOutcome (dikembalikan)."""
    steps = list(steps)

    def job(db, settings, job_id):
        db.execute(text("SELECT 1"))
        step = steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step

    return job


def run(factory, job_fn, recorder, settings=None, **kwargs):
    return run_job(
        "trello",
        factory,
        settings or pipeline(),
        job_fn=job_fn,
        sleep=recorder.sleep,
        notifier=recorder.notify,
        secrets=[SECRET],
        **kwargs,
    )


# --- runner (DIG-127) -------------------------------------------------------------------


def test_successful_job_is_recorded(jobs_db):
    rec = Recorder()
    job = run(
        jobs_db,
        scripted(JobOutcome(10, 4, {"b": {"inserted": 4}})),
        rec,
        trigger="schedule",
        triggered_by="cron",
    )

    assert job.status == "succeeded"
    assert (job.attempts, job.rows_read, job.rows_written) == (1, 10, 4)
    assert job.details == {"b": {"inserted": 4}}
    assert job.finished_at is not None and job.error is None
    assert (job.trigger, job.triggered_by) == ("schedule", "cron")
    assert rec.sleeps == [] and rec.messages == []


def test_temporary_error_is_retried_with_growing_delay(jobs_db):
    rec = Recorder()
    job = run(
        jobs_db,
        scripted(httpx.ConnectError("putus"), TrelloRateLimitError("429"), JobOutcome(1, 1)),
        rec,
    )
    assert job.status == "succeeded"
    assert job.attempts == 3
    assert rec.sleeps == [5, 10]
    assert rec.messages == []


def test_permanent_error_fails_without_retry_and_notifies(jobs_db):
    rec = Recorder()
    job = run(jobs_db, scripted(TrelloAuthError(f"401 untuk token {SECRET}")), rec)

    assert job.status == "failed"
    assert job.attempts == 1
    assert rec.sleeps == []
    assert job.error.startswith("TrelloAuthError: 401")
    assert SECRET not in job.error
    assert len(rec.messages) == 1
    assert f"job #{job.job_id}" in rec.messages[0]
    assert SECRET not in rec.messages[0]


def test_job_fails_after_max_attempts(jobs_db, caplog):
    rec = Recorder()
    errors = [httpx.ConnectError(f"putus {i}") for i in range(3)]
    with caplog.at_level(logging.INFO, logger="app.pipeline"):
        job = run(jobs_db, scripted(*errors), rec, settings=pipeline(import_max_attempts=3))

    assert job.status == "failed"
    assert job.attempts == 3
    assert rec.sleeps == [5, 10]
    assert job.error == "ConnectError: putus 2"
    assert len(rec.messages) == 1

    failed = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(failed) == 1
    assert (failed[0].job_id, failed[0].status, failed[0].attempts) == (job.job_id, "failed", 3)
    retries = [r for r in caplog.records if r.getMessage() == "percobaan job gagal"]
    assert [r.will_retry for r in retries] == [True, True, False]


def test_failed_attempt_is_rolled_back(jobs_db):
    """Tulisan dari percobaan yang gagal tidak boleh tertinggal di staging."""

    def job(db, settings, job_id):
        db.execute(
            text(
                "INSERT INTO trello_list_mapping (list_id, list_name)"
                " VALUES ('aaaaaaaaaaaaaaaaaaaaaaaa', 'To Do')"
            )
        )
        raise httpx.ReadTimeout("lambat")

    run(jobs_db, job, Recorder(), settings=pipeline(import_max_attempts=2))
    with jobs_db() as db:
        assert db.scalar(text("SELECT count(*) FROM trello_list_mapping")) == 0


def test_second_job_for_same_source_is_refused_while_running(jobs_db):
    rec = Recorder()

    def job(db, settings, job_id):
        with pytest.raises(JobAlreadyRunning) as info:
            run(jobs_db, scripted(JobOutcome(0, 0)), rec)
        assert info.value.job_id is not None
        return JobOutcome(0, 0)

    first = run(jobs_db, job, rec)
    assert first.status == "succeeded"
    with jobs_db() as db:
        assert db.scalar(text("SELECT count(*) FROM import_job")) == 1


def test_stale_running_job_is_closed_before_new_run(jobs_db):
    with jobs_db() as db:
        db.execute(
            text(
                "INSERT INTO import_job (source, trigger, status, started_at)"
                " VALUES ('trello', 'schedule', 'running', now() - interval '3 hours')"
            )
        )
        db.commit()

    job = run(jobs_db, scripted(JobOutcome(0, 0)), Recorder())
    assert job.status == "succeeded"
    with jobs_db() as db:
        stale = db.query(ImportJob).filter(ImportJob.job_id != job.job_id).one()
    assert stale.status == "failed"
    assert stale.finished_at is not None
    assert "lebih dari 120 menit" in stale.error


def test_recent_running_job_is_not_closed(jobs_db):
    with jobs_db() as db:
        db.execute(
            text(
                "INSERT INTO import_job (source, trigger, status, started_at)"
                " VALUES ('trello', 'schedule', 'running', now() - interval '5 minutes')"
            )
        )
        db.commit()
    with pytest.raises(JobAlreadyRunning):
        run(jobs_db, scripted(JobOutcome(0, 0)), Recorder())


def test_other_source_can_run_at_the_same_time(jobs_db):
    with jobs_db() as db:
        db.execute(
            text(
                "INSERT INTO import_job (source, trigger, status)"
                " VALUES ('teamgit', 'manual', 'running')"
            )
        )
        db.commit()
    assert run(jobs_db, scripted(JobOutcome(0, 0)), Recorder()).status == "succeeded"


def test_job_receives_its_own_job_id(jobs_db):
    """job_id dipakai sebagai import_job_id di tabel staging (DIG-113)."""
    seen = []

    def job(db, settings, job_id):
        seen.append(job_id)
        if len(seen) == 1:
            raise httpx.ConnectError("putus")
        return JobOutcome(0, 0)

    recorded = run(jobs_db, job, Recorder())
    assert seen == [recorded.job_id, recorded.job_id]  # sama di setiap percobaan


def test_job_closed_as_stale_while_running_is_not_overwritten(jobs_db):
    """Job sah yang lebih lama dari IMPORT_STALE_MINUTES ditutup failed oleh job berikutnya;
    saat selesai, catatan itu tidak ditimpa menjadi succeeded (review #34)."""
    rec = Recorder()

    def job(db, settings, job_id):
        with jobs_db() as other:
            other.execute(
                text(
                    "UPDATE import_job SET status = 'failed', finished_at = now(),"
                    " error = 'ditutup macet' WHERE job_id = :id"
                ),
                {"id": job_id},
            )
            other.commit()
        return JobOutcome(5, 5)

    finished = run(jobs_db, job, rec)
    assert (finished.status, finished.error, finished.rows_written) == (
        "failed",
        "ditutup macet",
        None,
    )
    assert len(rec.messages) == 1
    assert "sudah ditutup sebagai macet" in rec.messages[0]
    assert "IMPORT_STALE_MINUTES" in rec.messages[0]


# --- tabel import_job (DIG-128) -----------------------------------------------------------


@pytest.mark.parametrize(
    "values",
    [
        "('jira', 'manual', 'running', NULL, 1)",
        "('trello', 'cron', 'running', NULL, 1)",
        "('trello', 'manual', 'selesai', now(), 1)",
        "('trello', 'manual', 'running', now(), 1)",
        "('trello', 'manual', 'failed', NULL, 1)",
        "('trello', 'manual', 'failed', now(), 0)",
    ],
)
def test_invalid_job_rows_are_rejected(jobs_db, values):
    with jobs_db() as db, pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO import_job (source, trigger, status, finished_at, attempts)"
                f" VALUES {values}"
            )
        )
        db.flush()


# --- job Trello ujung ke ujung --------------------------------------------------------------


def test_trello_job_writes_staging(jobs_db, monkeypatch):
    board = json.loads(FIXTURE.read_text(encoding="utf-8"))
    requested = []

    def fake_export(self, board_id):
        requested.append(board_id)
        return board

    monkeypatch.setattr(TrelloClient, "fetch_board_export", fake_export)
    trello = TrelloSettings(_env_file=None, api_enabled=True, api_key="k", api_token=SECRET)

    def job(db, settings, job_id):
        return import_trello(db, settings, job_id, trello_settings=trello)

    first = run(jobs_db, job, Recorder())
    second = run(jobs_db, job, Recorder())

    assert requested == ["AbCd1234", "AbCd1234"]
    assert first.status == second.status == "succeeded"
    assert first.rows_read > 0 and first.rows_written == first.rows_read
    assert second.rows_written == 0  # impor ulang tidak menggandakan baris
    detail = second.details["AbCd1234"]
    assert detail["already_present"] == first.rows_read
    with jobs_db() as db:
        stored = db.scalar(text("SELECT count(*) FROM staging_trello_action"))
    assert stored == first.rows_written


# --- endpoint pemantauan (DIG-128) ------------------------------------------------------------


def seed_jobs(factory):
    rec = Recorder()
    ok = run(factory, scripted(JobOutcome(3, 2)), rec)
    failed = run(factory, scripted(TrelloAuthError("401")), rec)
    return ok, failed


def test_list_jobs_newest_first_with_filters(client, session_factory):
    with session_factory() as db:
        db.execute(text("TRUNCATE import_job"))
        db.commit()
    ok, failed = seed_jobs(session_factory)

    body = client.get("/api/v1/data/import-jobs").json()
    assert [j["job_id"] for j in body] == [failed.job_id, ok.job_id]
    assert body[0]["status"] == "failed" and body[0]["error"] == "TrelloAuthError: 401"

    only_failed = client.get("/api/v1/data/import-jobs", params={"status": "failed"}).json()
    assert [j["job_id"] for j in only_failed] == [failed.job_id]
    assert client.get("/api/v1/data/import-jobs", params={"source": "teamgit"}).json() == []
    assert len(client.get("/api/v1/data/import-jobs", params={"limit": 1}).json()) == 1
    assert client.get("/api/v1/data/import-jobs", params={"status": "x"}).status_code == 422


def test_get_job_detail_and_not_found(client, session_factory):
    ok, _ = seed_jobs(session_factory)
    body = client.get(f"/api/v1/data/import-jobs/{ok.job_id}").json()
    assert (body["rows_read"], body["rows_written"], body["attempts"]) == (3, 2, 1)
    assert client.get("/api/v1/data/import-jobs/999999").status_code == 404


@pytest.mark.parametrize(("role", "code"), [("system_analyst", 200), ("anggota_tim", 403)])
def test_job_monitoring_needs_data_quality_permission(client, session_factory, role, code):
    with session_factory() as db:
        token = make_token(db, f"pantau-{role}", [role])
    response = client.get("/api/v1/data/import-jobs", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == code


def test_running_job_older_than_stale_limit_is_flagged(client, session_factory):
    with session_factory() as db:
        db.execute(text("TRUNCATE import_job"))
        db.execute(
            text(
                "INSERT INTO import_job (source, trigger, status, started_at, finished_at) VALUES"
                " ('trello', 'schedule', 'running', now() - interval '3 hours', NULL),"
                " ('teamgit', 'schedule', 'running', now() - interval '5 minutes', NULL),"
                " ('project_plan', 'manual', 'succeeded', now() - interval '3 hours', now())"
            )
        )
        db.commit()

    stale = {j["source"]: j["stale"] for j in client.get("/api/v1/data/import-jobs").json()}
    assert stale == {"trello": True, "teamgit": False, "project_plan": False}

    old = client.get("/api/v1/data/import-jobs", params={"source": "trello"}).json()[0]
    assert client.get(f"/api/v1/data/import-jobs/{old['job_id']}").json()["stale"] is True
