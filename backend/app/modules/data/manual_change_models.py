"""Jejak perubahan task dari aplikasi (DIG-162, tabel internal J&C di DATA_CONTRACT 7.2).

Satu baris = satu kolom task yang diubah lewat aplikasi, bukan lewat impor: ubah status
(DIG-161), efek CR (DIG-150), atau blocker (DIG-153). Impor berikutnya (ETL DIG-134) membaca
baris yang belum punya `resolution` supaya perubahan itu tidak tertimpa tanpa konfirmasi
(AC DIG-36). Bukan kolom baru di D-05, jadi tidak mengubah kontrak dengan tWinner.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TRACKED_FIELDS = ("status", "priority_rank", "actual_start", "actual_finish", "dod_fulfilled")
SOURCES = ("status_update", "change_event", "blocker")
RESOLUTIONS = ("kept", "import_taken", "caught_up")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TaskManualChange(Base):
    __tablename__ = "task_manual_change"
    __table_args__ = (
        CheckConstraint(_in("field", TRACKED_FIELDS), name="field_valid"),
        CheckConstraint(_in("source", SOURCES), name="source_valid"),
        CheckConstraint(
            f"resolution IS NULL OR {_in('resolution', RESOLUTIONS)}", name="resolution_valid"
        ),
        CheckConstraint("(resolution IS NULL) = (resolved_at IS NULL)", name="resolved_together"),
        # Perubahan yang masih menunggu impor dibaca per task dan kolom.
        Index(
            "ix_task_manual_change_open",
            "task_id",
            "field",
            postgresql_where="resolution IS NULL",
        ),
    )

    change_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.task_id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(20))
    old_value: Mapped[str | None] = mapped_column(String(50))
    new_value: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(20))
    ref: Mapped[str | None] = mapped_column(String(20))
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.user_id", ondelete="SET NULL")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolution: Mapped[str | None] = mapped_column(String(20))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
