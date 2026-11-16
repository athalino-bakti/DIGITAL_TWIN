"""Menjalankan job impor dari terminal, cron, atau systemd timer (DIG-127).

Dari folder backend:
    python -m app.pipeline.run trello
    python -m app.pipeline.run trello --trigger schedule   # dari cron/systemd timer

Kode keluar: 0 berhasil, 1 gagal, 2 job sumber yang sama masih berjalan.
Contoh jadwal ada di docs/IMPORT_PIPELINE.md.
"""

import argparse
import getpass
import logging
import sys

from app.pipeline.config import get_pipeline_settings
from app.pipeline.jobs import JOBS
from app.pipeline.logging import configure_logging
from app.pipeline.runner import JobAlreadyRunning, run_job


def main(argv: list[str] | None = None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(description="Jalankan satu job impor")
    parser.add_argument("source", choices=sorted(JOBS))
    parser.add_argument("--trigger", choices=["manual", "schedule"], default="manual")
    args = parser.parse_args(argv)

    settings = get_pipeline_settings()
    configure_logging(settings.log_format, settings.log_level)
    if session_factory is None:
        from app.db.session import SessionLocal as session_factory

    try:
        job = run_job(
            args.source,
            session_factory,
            settings,
            trigger=args.trigger,
            triggered_by=getpass.getuser(),
        )
    except JobAlreadyRunning as exc:
        logging.getLogger("app.pipeline").warning(str(exc))
        return 2
    return 0 if job.status == "succeeded" else 1


if __name__ == "__main__":
    sys.exit(main())
