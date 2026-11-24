"""Jejak audit perubahan final sources (DIG-222, tabel internal J&C di DATA_CONTRACT 7.2 dan 8).

Satu baris = satu perubahan pada satu baris tabel final sources. Kolom yang berubah terlihat dari
kunci `before`/`after` (insert: seluruh baris di `after`; delete: seluruh baris di `before`;
update: hanya kolom yang berubah di keduanya). D-01 sampai D-11 tidak mendapat kolom audit.

Tabel ini append-only bagi aplikasi: role `jc_app` hanya boleh SELECT dan INSERT (migrasi 0026).
`task_manual_change` (DIG-162) tetap terpisah karena menyimpan status konflik impor, bukan riwayat.
"""

from datetime import datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

AUDIT_ACTIONS = ("insert", "update", "delete", "import", "export")
AUDIT_SOURCES = ("form", "project_plan", "trello", "teamgit", "etl", "sistem")
SYSTEM_ACTOR = "sistem"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint(_in("action", AUDIT_ACTIONS), name="action_valid"),
        CheckConstraint(_in("source", AUDIT_SOURCES), name="source_valid"),
        CheckConstraint(
            "(action <> 'insert' OR before IS NULL)"
            " AND (action <> 'delete' OR after IS NULL)"
            " AND (action <> 'update' OR (before IS NOT NULL AND after IS NOT NULL))",
            name="values_match_action",
        ),
        Index("ix_audit_log_entity", "entity", "entity_id", "occurred_at"),
        Index("ix_audit_log_occurred_at", "occurred_at"),
        Index("ix_audit_log_import_job_id", "import_job_id"),
    )

    audit_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.user_id", ondelete="SET NULL")
    )
    actor_label: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(10))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(20))
    import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.job_id", ondelete="SET NULL")
    )
    # none_as_null: None disimpan sebagai SQL NULL, bukan JSON null, agar CHECK di atas berlaku.
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))
    note: Mapped[str | None] = mapped_column(String(500))
