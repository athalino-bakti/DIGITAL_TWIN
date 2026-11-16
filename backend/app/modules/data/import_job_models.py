"""Catatan setiap job impor (DIG-128, tabel internal J&C di DATA_CONTRACT 7.2).

Satu baris = satu kali job dijalankan (manual atau terjadwal), apa pun hasilnya. Kolom
`status` dipakai untuk pemantauan: `running` saat berjalan, lalu `succeeded` atau `failed`.

Paling banyak satu job `running` per sumber (index unik parsial), sehingga jadwal yang
tumpang tindih atau dua orang yang menjalankan impor bersamaan tidak saling menimpa.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JOB_SOURCES = ("trello", "project_plan", "teamgit")
JOB_TRIGGERS = ("manual", "schedule")
JOB_STATUSES = ("running", "succeeded", "failed")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class ImportJob(Base):
    __tablename__ = "import_job"
    __table_args__ = (
        CheckConstraint(_one_of("source", JOB_SOURCES), name="source_valid"),
        CheckConstraint(_one_of("trigger", JOB_TRIGGERS), name="trigger_valid"),
        CheckConstraint(_one_of("status", JOB_STATUSES), name="status_valid"),
        CheckConstraint("attempts >= 1", name="attempts_positive"),
        CheckConstraint("(status = 'running') = (finished_at IS NULL)", name="finished_when_done"),
        Index("ix_import_job_source_started_at", "source", "started_at"),
        Index(
            "uq_import_job_one_running_per_source",
            "source",
            unique=True,
            postgresql_where=text("status = 'running'"),
        ),
    )

    job_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(String(20))
    trigger: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer, server_default="1")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int | None] = mapped_column(Integer)
    rows_written: Mapped[int | None] = mapped_column(Integer)
    # Ringkasan hasil per sumber (misalnya per papan Trello) atau parameter job.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String(100))
