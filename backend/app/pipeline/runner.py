"""Menjalankan satu job impor dan mencatatnya di import_job (DIG-127, DIG-128, DIG-129).

Alur:
1. Job `running` dari sumber yang sama yang lebih tua dari IMPORT_STALE_MINUTES ditutup gagal
   (prosesnya kemungkinan mati di tengah jalan).
2. Baris baru `running` dibuat. Bila sudah ada job sumber itu yang berjalan, index unik
   menolak dan runner melempar `JobAlreadyRunning`.
3. Job dijalankan. Error sementara (`is_transient`) dicoba ulang sampai IMPORT_MAX_ATTEMPTS
   dengan jeda bertambah dua kali lipat; error lain langsung gagal.
4. Baris job ditutup `succeeded` atau `failed`. Saat gagal, log ERROR dan notifikasi dikirim.

Pesan error disimpan setelah nilai rahasia (token, URL webhook) disamarkan.
"""

import logging
import time
from collections.abc import Callable, Iterable
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.data.import_job_models import ImportJob
from app.pipeline.config import PipelineSettings
from app.pipeline.jobs import JOBS, JobFn, is_transient
from app.pipeline.notify import send_notification

logger = logging.getLogger("app.pipeline")
MAX_ERROR = 2000


class JobAlreadyRunning(Exception):
    def __init__(self, source: str, job_id: int | None) -> None:
        super().__init__(f"Job {source} masih berjalan (job_id {job_id})")
        self.source = source
        self.job_id = job_id


def redact(message: str, secrets: Iterable[str | None]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 4:
            message = message.replace(secret, "***")
    return message[:MAX_ERROR]


def default_secrets(settings: PipelineSettings) -> list[str]:
    from app.integrations.teamgit.config import get_teamgit_settings
    from app.integrations.trello.config import get_trello_settings

    trello, teamgit = get_trello_settings(), get_teamgit_settings()
    values = [trello.api_key, trello.api_token, teamgit.token, settings.notify_webhook_url]
    return [v.get_secret_value() for v in values if v is not None]


def close_stale_jobs(db: Session, source: str, stale_minutes: int) -> int:
    result = db.execute(
        update(ImportJob)
        .where(
            ImportJob.source == source,
            ImportJob.status == "running",
            ImportJob.started_at < func.now() - timedelta(minutes=stale_minutes),
        )
        .values(
            status="failed",
            finished_at=func.now(),
            error=f"Terhenti tanpa selesai lebih dari {stale_minutes} menit (proses mati?)",
        )
    )
    db.commit()
    return result.rowcount


def _start(db: Session, source: str, trigger: str, triggered_by: str | None) -> ImportJob:
    job = ImportJob(source=source, trigger=trigger, status="running", triggered_by=triggered_by)
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        running = db.scalar(
            select(ImportJob.job_id).where(
                ImportJob.source == source, ImportJob.status == "running"
            )
        )
        raise JobAlreadyRunning(source, running) from exc
    return job


def run_job(
    source: str,
    session_factory: sessionmaker,
    settings: PipelineSettings,
    trigger: str = "manual",
    triggered_by: str | None = None,
    job_fn: JobFn | None = None,
    sleep: Callable[[float], None] = time.sleep,
    notifier: Callable[[PipelineSettings, str], bool] = send_notification,
    secrets: Iterable[str] | None = None,
) -> ImportJob:
    job_fn = job_fn or JOBS[source]
    secrets = list(default_secrets(settings) if secrets is None else secrets)

    with session_factory() as db:
        if closed := close_stale_jobs(db, source, settings.import_stale_minutes):
            logger.warning("job macet ditutup", extra={"source": source, "closed": closed})
        job = _start(db, source, trigger, triggered_by)

    log = {"job_id": job.job_id, "source": source, "trigger": trigger}
    logger.info("job impor dimulai", extra=log)
    started = time.monotonic()
    outcome, error = None, None

    for attempt in range(1, settings.import_max_attempts + 1):
        with session_factory() as work:
            try:
                outcome = job_fn(work, settings)
                break
            except Exception as exc:  # noqa: BLE001 - semua error dicatat di import_job
                work.rollback()
                error = redact(f"{type(exc).__name__}: {exc}", secrets)
                retry = is_transient(exc) and attempt < settings.import_max_attempts
                logger.warning(
                    "percobaan job gagal",
                    extra={**log, "attempt": attempt, "will_retry": retry, "error": error},
                )
                if not retry:
                    break
        with session_factory() as db:
            db.execute(
                update(ImportJob).where(ImportJob.job_id == job.job_id).values(attempts=attempt + 1)
            )
            db.commit()
        sleep(settings.import_retry_delay_seconds * 2 ** (attempt - 1))

    duration_ms = round((time.monotonic() - started) * 1000)
    with session_factory() as db:
        job = db.get(ImportJob, job.job_id)
        job.finished_at = func.now()
        if outcome is not None:
            job.status = "succeeded"
            job.rows_read, job.rows_written = outcome.rows_read, outcome.rows_written
            job.details = outcome.details
        else:
            job.status = "failed"
            job.error = error
        db.commit()
        db.refresh(job)

    summary = {**log, "status": job.status, "attempts": job.attempts, "duration_ms": duration_ms}
    if job.status == "succeeded":
        logger.info(
            "job impor selesai",
            extra={**summary, "rows_read": job.rows_read, "rows_written": job.rows_written},
        )
    else:
        logger.error("job impor gagal", extra={**summary, "error": job.error})
        notifier(
            settings,
            f"[J&C] Impor {source} gagal (job #{job.job_id}, {job.attempts} percobaan, "
            f"pemicu {trigger}): {job.error}",
        )
    return job
