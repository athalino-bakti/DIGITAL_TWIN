"""Hasil pemeriksaan kualitas data per impor (DIG-145, tabel internal J&C di DATA_CONTRACT 7.2).

Keduanya disimpan dari `quality.engine.Report` untuk satu `import_job`:

- `data_quality_result`: satu baris per aturan per sumber (`Report.summaries`), dasar persentase
  lolos per karakteristik ISO/IEC 25012 (AC DIG-32);
- `rejected_row`: satu baris per temuan (`Report.findings`), `tolak` maupun `peringatan`, supaya
  peringatan bisa ditampilkan terpisah dari penolakan.

Menghapus job menghapus hasilnya (CASCADE). Memeriksa ulang job yang sama mengganti hasil lama.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CHARACTERISTICS = ("completeness", "consistency", "currentness", "traceability")
LEVELS = ("tolak", "peringatan")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class DataQualityResult(Base):
    __tablename__ = "data_quality_result"
    __table_args__ = (
        CheckConstraint(_in("characteristic", CHARACTERISTICS), name="characteristic_valid"),
        CheckConstraint(_in("level", LEVELS), name="level_valid"),
        CheckConstraint("violated >= 0 AND violated <= checked", name="violated_range"),
        UniqueConstraint("job_id", "source", "rule_id"),
    )

    result_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_job.job_id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(40))
    rule_id: Mapped[str] = mapped_column(String(20))
    table_name: Mapped[str] = mapped_column(String(40))
    characteristic: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(10))
    rule_text: Mapped[str] = mapped_column(Text)
    checked: Mapped[int] = mapped_column(Integer)
    violated: Mapped[int] = mapped_column(Integer)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RejectedRow(Base):
    __tablename__ = "rejected_row"
    __table_args__ = (
        CheckConstraint(_in("characteristic", CHARACTERISTICS), name="characteristic_valid"),
        CheckConstraint(_in("level", LEVELS), name="level_valid"),
        # Daftar baris ditolak dibaca per job, tolak dulu.
        Index("ix_rejected_row_job_id_level", "job_id", "level"),
    )

    rejected_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_job.job_id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(40))
    table_name: Mapped[str] = mapped_column(String(40))
    row_number: Mapped[int | None] = mapped_column(Integer)
    row_key: Mapped[str | None] = mapped_column(Text)
    rule_id: Mapped[str] = mapped_column(String(20))
    characteristic: Mapped[str] = mapped_column(String(20))
    level: Mapped[str] = mapped_column(String(10))
    column_name: Mapped[str | None] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
