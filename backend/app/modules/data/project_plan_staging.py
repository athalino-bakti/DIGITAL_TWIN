"""Simpan hasil parser Project Plan (DIG-114) ke staging_project_plan (DIG-113).

Fungsi di sini tidak melakukan commit; pemanggil (job impor) yang menentukan batas transaksi.
"""

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.integrations.project_plan.parser import ProjectPlanParseResult
from app.modules.data.import_job_models import ImportJob
from app.modules.data.staging_models import StagingProjectPlan


def save_project_plan(
    db: Session, result: ProjectPlanParseResult, job_id: int, project_id: str, file_name: str
) -> int:
    """Tulis setiap baris sebagai batch baru milik `job_id`. Mengembalikan jumlah baris."""
    rows = [
        {
            "import_job_id": job_id,
            "row_number": row.row_number,
            "project_id": project_id,
            "file_name": file_name,
            "sheet_name": result.table.sheet_name,
            **row.values,
            "raw": row.raw,
        }
        for row in result.rows
    ]
    if rows:
        db.execute(insert(StagingProjectPlan), rows)
    return len(rows)


def same_file_job_id(db: Session, project_id: str, file_sha256: str) -> int | None:
    """Job impor sukses terakhir proyek ini bila berkasnya identik (peringatan unggah ganda)."""
    last = db.execute(
        select(ImportJob.job_id, ImportJob.details["file_sha256"].astext)
        .where(
            ImportJob.source == "project_plan",
            ImportJob.status == "succeeded",
            ImportJob.details["project_id"].astext == project_id,
        )
        .order_by(ImportJob.job_id.desc())
        .limit(1)
    ).first()
    return last.job_id if last and last[1] == file_sha256 else None
