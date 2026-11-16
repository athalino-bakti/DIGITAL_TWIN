"""Event log untuk process mining (DIG-164), tabel internal J&C (DATA_CONTRACT 7.2).

Satu task menjadi satu case (`case_id` = `task_id`), dan satu baris sumber (action Trello atau
kejadian D-10) menjadi satu event. Isinya dibentuk ulang seluruhnya oleh
`app.modules.data.event_log.rebuild_event_log`, sehingga tabel ini bukan sumber kebenaran:
data asli tetap di staging dan final sources.

Atribut XES (IEEE 1849-2023): `activity` = concept:name, `event_time` = time:timestamp, dan
`resource_id` = org:resource. Selama tabel alias identitas (DIG-24) belum ada, `resource_id`
kosong dan akun pelaku disimpan di `actor_source_id` dan `actor_name`.

`case_id` sengaja tanpa foreign key: kartu Trello bisa berisi task yang belum dimuat ke D-05.
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ACTIVITY_KINDS = ("created", "status", "archived", "deleted", "assignment", "change_event")
EVENT_SOURCES = ("trello", "change_event")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class EventLogEntry(Base):
    __tablename__ = "event_log"
    __table_args__ = (
        CheckConstraint(_one_of("activity_kind", ACTIVITY_KINDS), name="activity_kind_valid"),
        CheckConstraint(_one_of("source", EVENT_SOURCES), name="source_valid"),
        # Satu baris sumber menjadi tepat satu event; bangun ulang tidak menggandakan.
        UniqueConstraint("source", "source_ref"),
        Index("ix_event_log_case_id_event_time", "case_id", "event_time"),
        Index("ix_event_log_project_id_event_time", "project_id", "event_time"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(20))
    project_id: Mapped[str | None] = mapped_column(String(20))
    activity: Mapped[str] = mapped_column(String(100))
    activity_kind: Mapped[str] = mapped_column(String(20))
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resource_id: Mapped[str | None] = mapped_column(
        ForeignKey("resources.resource_id", ondelete="SET NULL")
    )
    actor_source_id: Mapped[str | None] = mapped_column(String(50))
    actor_name: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20))
    source_ref: Mapped[str] = mapped_column(String(50))
