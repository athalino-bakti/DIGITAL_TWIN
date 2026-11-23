"""Simpan hasil validator ke data_quality_result dan rejected_row (DIG-145)."""

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.data.quality.engine import Report
from app.modules.data.quality_models import DataQualityResult, RejectedRow


def save_report(db: Session, job_id: int, report: Report) -> tuple[int, int]:
    """Ganti hasil kualitas job `job_id` dengan isi `report`. Tidak commit.

    Mengembalikan (jumlah aturan, jumlah temuan) yang disimpan.
    """
    db.execute(delete(DataQualityResult).where(DataQualityResult.job_id == job_id))
    db.execute(delete(RejectedRow).where(RejectedRow.job_id == job_id))
    db.add_all(
        DataQualityResult(
            job_id=job_id,
            source=s.source,
            rule_id=s.rule_id,
            table_name=s.table,
            characteristic=s.characteristic,
            level=s.level,
            rule_text=s.text,
            checked=s.checked,
            violated=s.violated,
        )
        for s in report.summaries
    )
    db.add_all(
        RejectedRow(
            job_id=job_id,
            source=f.source,
            table_name=f.table,
            row_number=f.row_number,
            row_key=f.row_key,
            rule_id=f.rule_id,
            characteristic=f.characteristic,
            level=f.level,
            column_name=f.column,
            value=f.value,
            message=f.message,
        )
        for f in report.findings
    )
    return len(report.summaries), len(report.findings)
