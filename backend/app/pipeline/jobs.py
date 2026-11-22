"""Isi job impor per sumber (DIG-127).

Setiap job menerima satu Session, pengaturan, dan `job_id` baris import_job yang sedang
berjalan, menulis ke staging, lalu commit sendiri. `job_id` disediakan untuk kolom
`import_job_id` di tabel staging (DIG-113), supaya setiap baris staging bisa ditelusuri ke
job yang menulisnya. Bila job melempar
error, runner melakukan rollback dan memutuskan apakah dicoba ulang (`is_transient`).

Sumber terjadwal di JOBS: Trello lewat API. Project Plan (DIG-25) tidak punya sumber yang bisa
ditarik terjadwal; endpoint unggah menjalankan `run_job("project_plan", job_fn=...)` dengan isi
berkas yang sudah diterima. TeamGit (DIG-27) didaftarkan begitu importernya ada.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.integrations.trello.client import (
    TrelloAuthError,
    TrelloDisabledError,
    TrelloError,
    TrelloNotFoundError,
    TrelloRateLimitError,
    client_from_settings,
)
from app.integrations.trello.config import TrelloSettings
from app.integrations.trello.parser import parse_board_export
from app.modules.data.trello_staging import save_trello_import
from app.pipeline.config import PipelineSettings


class PermanentJobError(Exception):
    """Kesalahan konfigurasi atau data yang tidak akan beres dengan dicoba ulang."""


@dataclass
class JobOutcome:
    rows_read: int
    rows_written: int
    details: dict[str, Any] = field(default_factory=dict)


def is_transient(exc: BaseException) -> bool:
    """True untuk error yang mungkin hilang sendiri: jaringan, 429, 5xx, basis data putus."""
    if isinstance(exc, (TrelloAuthError, TrelloNotFoundError, TrelloDisabledError)):
        return False
    if isinstance(exc, (TrelloRateLimitError, TrelloError)):
        return True  # TrelloError lain: jaringan, 5xx yang sudah dicoba ulang client, non-JSON
    return isinstance(exc, (httpx.TransportError, OperationalError))


def import_trello(
    db: Session,
    settings: PipelineSettings,
    job_id: int | None = None,
    trello_settings: TrelloSettings | None = None,
    transport: httpx.BaseTransport | None = None,
) -> JobOutcome:
    """Ambil setiap papan di TRELLO_BOARD_IDS lewat API dan simpan ke staging, satu transaksi."""
    boards = settings.board_ids
    if not boards:
        raise PermanentJobError("TRELLO_BOARD_IDS kosong, tidak ada papan yang diimpor")
    try:
        client = client_from_settings(trello_settings, transport=transport)
    except TrelloDisabledError as exc:
        raise PermanentJobError(str(exc)) from exc

    outcome = JobOutcome(rows_read=0, rows_written=0)
    with client:
        for board in boards:
            parsed = parse_board_export(client.fetch_board_export(board))
            saved = save_trello_import(db, parsed, job_id)
            outcome.rows_read += len(parsed.actions)
            outcome.rows_written += saved.inserted
            outcome.details[board] = {
                "board_id": parsed.board_id,
                "actions": len(parsed.actions),
                "inserted": saved.inserted,
                "already_present": saved.already_present,
                "lists": saved.lists_seen,
                "skipped": dict(parsed.report.skipped_by_reason()),
            }
    db.commit()
    return outcome


JobFn = Callable[[Session, PipelineSettings, int], JobOutcome]
JOBS: dict[str, JobFn] = {"trello": import_trello}
