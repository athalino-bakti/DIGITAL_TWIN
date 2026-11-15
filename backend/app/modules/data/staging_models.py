"""Tabel internal J&C untuk impor Trello (DIG-117), bukan bagian Data Dictionary D-01 s.d. D-11.

`staging_trello_action` menyimpan action Trello apa adanya, satu baris per action. Id action
Trello unik global sehingga menjadi primary key; impor ulang dari berkas ekspor yang tumpang
tindih atau dari API tidak menambah baris (lihat `app.modules.data.trello_staging`).

`trello_list_mapping` memetakan list per papan ke status dan phase task. Pemetaan memakai id
list, bukan nama, karena nama list bisa diganti (`updateList`) dan dua list boleh bernama sama.
`list_name` hanya nama terakhir yang terlihat saat impor, untuk ditampilkan di UI (DIG-120).
"""

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.data.enums import TaskPhase, TaskStatus
from app.modules.data.models import matches, one_of

# Id objek Trello (papan, list, kartu, anggota, action): 24 karakter heksadesimal huruf kecil.
TRELLO_ID_PATTERN = "^[0-9a-f]{24}$"
TrelloId = String(24)


class StagingTrelloAction(Base):
    __tablename__ = "staging_trello_action"
    __table_args__ = (
        CheckConstraint(matches("action_id", TRELLO_ID_PATTERN), name="action_id_format"),
        Index("ix_staging_trello_action_card_id_action_date", "card_id", "action_date"),
    )

    action_id: Mapped[str] = mapped_column(TrelloId, primary_key=True)
    action_type: Mapped[str] = mapped_column(String(50))
    action_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    board_id: Mapped[str] = mapped_column(TrelloId)
    card_id: Mapped[str | None] = mapped_column(TrelloId)
    card_name: Mapped[str | None] = mapped_column(Text)
    # Posisi sebelum dan sesudah action: listBefore/listAfter pada updateCard yang memindahkan
    # kartu, list pada createCard dan sejenisnya, serta nama lama dan baru pada updateList.
    list_before_id: Mapped[str | None] = mapped_column(TrelloId)
    list_before_name: Mapped[str | None] = mapped_column(Text)
    list_after_id: Mapped[str | None] = mapped_column(TrelloId)
    list_after_name: Mapped[str | None] = mapped_column(Text)
    member_creator_id: Mapped[str | None] = mapped_column(TrelloId)
    member_creator_username: Mapped[str | None] = mapped_column(String(100))
    member_creator_full_name: Mapped[str | None] = mapped_column(String(200))
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # Kolom batch impor (import_job_id + FK) ditambahkan DIG-113 saat tabel import_job ada.


class TrelloListMapping(Base):
    __tablename__ = "trello_list_mapping"
    __table_args__ = (
        CheckConstraint(one_of("status", TaskStatus), name="status_valid"),
        CheckConstraint(one_of("phase", TaskPhase), name="phase_valid"),
    )

    board_id: Mapped[str] = mapped_column(TrelloId, primary_key=True)
    list_id: Mapped[str] = mapped_column(TrelloId, primary_key=True)
    list_name: Mapped[str] = mapped_column(Text)
    # Kosong berarti list belum dipetakan.
    status: Mapped[str | None] = mapped_column(String(20))
    phase: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
