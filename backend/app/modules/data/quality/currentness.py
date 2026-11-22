"""Currentness per sumber impor (DIG-143), dihitung terhadap `as_of` agar deterministik.

Per sumber di import_job:
- `last_success_at`: `finished_at` job `succeeded` terakhir sampai akhir hari `as_of` (WIB);
- `import_age_days`: `as_of` dikurangi tanggal impor itu;
- `newest_source_at`: aksi terbaru di staging sumber itu sampai `as_of`. Hanya Trello yang punya
  (`action_date`). Project Plan tidak membawa cap waktu pembaruan sumber, dan TeamGit belum
  punya staging;
- `source_lag_days`: impor terakhir dikurangi aksi terbaru, yaitu selisih impor terakhir dengan
  pembaruan sumber;
- `data_age_days`: `as_of` dikurangi aksi terbaru.

DQ-CUR-001 memberi peringatan bila sumber belum pernah diimpor dengan sukses, atau impor
terakhirnya lebih dari MAX_IMPORT_AGE_DAYS hari. Kontrak data bagian 3 menetapkan ETL paling
sedikit sekali seminggu.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.data.import_job_models import JOB_SOURCES, ImportJob
from app.modules.data.quality.engine import (
    PERINGATAN,
    Finding,
    Report,
    Rule,
    RuleSummary,
    register,
)
from app.modules.data.staging_models import StagingTrelloAction

WIB = timezone(timedelta(hours=7))
MAX_IMPORT_AGE_DAYS = 7
RULE = register(
    Rule(
        "DQ-CUR-001",
        "import_job",
        "currentness",
        PERINGATAN,
        f"Impor sukses terakhir paling lama {MAX_IMPORT_AGE_DAYS} hari sebelum as_of",
    )
)
# Kolom waktu sumber di staging; sumber yang tidak ada di sini tidak punya cap waktu sumber.
NEWEST_SOURCE = {"trello": StagingTrelloAction.action_date}


def _day(moment: datetime | None) -> date | None:
    return moment.astimezone(WIB).date() if moment else None


def measure(db: Session, as_of: date) -> list[dict[str, Any]]:
    """Satu baris ukuran currentness per sumber impor."""
    until = datetime.combine(as_of + timedelta(days=1), time(), WIB)
    rows = []
    for source in JOB_SOURCES:
        last = db.scalar(
            select(func.max(ImportJob.finished_at)).where(
                ImportJob.source == source,
                ImportJob.status == "succeeded",
                ImportJob.finished_at < until,
            )
        )
        column = NEWEST_SOURCE.get(source)
        newest = db.scalar(select(func.max(column)).where(column < until)) if column else None
        last_day, newest_day = _day(last), _day(newest)
        rows.append(
            {
                "source": source,
                "as_of": as_of.isoformat(),
                "last_success_at": last.isoformat() if last else None,
                "import_age_days": (as_of - last_day).days if last_day else None,
                "newest_source_at": newest.isoformat() if newest else None,
                "source_lag_days": (last_day - newest_day).days
                if last_day and newest_day
                else None,
                "data_age_days": (as_of - newest_day).days if newest_day else None,
            }
        )
    return rows


def currentness_report(db: Session, as_of: date) -> Report:
    report = Report("import_job", currentness=measure(db, as_of))
    for row in report.currentness:
        age = row["import_age_days"]
        if age is None:
            message = f"Sumber {row['source']} belum pernah diimpor dengan sukses"
        elif age > MAX_IMPORT_AGE_DAYS:
            message = (
                f"Impor sukses terakhir {row['source']} {age} hari sebelum {as_of}, "
                f"lebih dari {MAX_IMPORT_AGE_DAYS} hari"
            )
        else:
            continue
        report.findings.append(
            Finding(
                RULE.rule_id,
                RULE.characteristic,
                RULE.level,
                "import_job",
                "import_job",
                None,
                row["source"],
                "finished_at",
                row["last_success_at"],
                message,
            )
        )
    report.summaries.append(
        RuleSummary(
            RULE.rule_id,
            "import_job",
            "import_job",
            RULE.characteristic,
            RULE.level,
            RULE.text,
            checked=len(report.currentness),
            violated=len(report.findings),
        )
    )
    return report
