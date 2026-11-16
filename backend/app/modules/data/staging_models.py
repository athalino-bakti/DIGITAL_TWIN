"""Tabel internal J&C untuk impor Trello (DIG-117), bukan bagian Data Dictionary D-01 s.d. D-11.

`staging_trello_action` menyimpan action Trello apa adanya, satu baris per action. Id action
Trello unik global sehingga menjadi primary key; impor ulang dari berkas ekspor yang tumpang
tindih atau dari API tidak menambah baris (lihat `app.modules.data.trello_staging`).

`trello_list_mapping` memetakan list per papan ke status dan phase task. Pemetaan memakai id
list, bukan nama, karena nama list bisa diganti (`updateList`) dan dua list boleh bernama sama.
`list_name` hanya nama terakhir yang terlihat saat impor, untuk ditampilkan di UI (DIG-120).

`staging_project_plan` (DIG-113) menyimpan baris Project Plan apa adanya, satu baris per baris
berkas per impor. Setiap unggahan adalah batch milik satu `import_job`; ETL DIG-29 memakai job
sukses terakhir per `project_id`.

Kolom `import_job_id` menunjuk job yang menulis baris itu:
- Project Plan: wajib, ON DELETE CASCADE (menghapus job menghapus batch-nya).
- Trello: boleh kosong (baris sebelum DIG-113), ON DELETE SET NULL. Action unik global dan
  dipakai event log, jadi tidak ikut terhapus. Action yang sudah ada tidak ditulis ulang, sehingga
  `import_job_id` adalah job pertama yang menyimpannya.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.data.enums import PROJECT_ID_PATTERN, TaskPhase, TaskStatus
from app.modules.data.import_job_models import ImportJob
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
    import_job_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey(ImportJob.job_id, ondelete="SET NULL")
    )


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


# Atribut hasil pemetaan kolom Project Plan, urut seperti templat (PLAN_HEADER). Semua teks mentah;
# normalisasi ke D-05/D-06 dikerjakan ETL DIG-29.
PROJECT_PLAN_FIELDS = (
    "task_code",
    "feature_name",
    "task_name",
    "role_label",
    "pic",
    "complexity_label",
    "priority",
    "estimated_days",
    "planned_start",
    "planned_finish",
    "actual_start",
    "actual_finish",
    "status_label",
    "depends_on",
    "notes",
)


class StagingProjectPlan(Base):
    __tablename__ = "staging_project_plan"
    __table_args__ = (
        CheckConstraint(matches("project_id", PROJECT_ID_PATTERN), name="project_id_format"),
        Index("ix_staging_project_plan_project_id_import_job_id", "project_id", "import_job_id"),
    )

    import_job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey(ImportJob.job_id, ondelete="CASCADE"), primary_key=True
    )
    # Nomor baris di berkas; baris judul kolom = baris 1, sama dengan nomor baris di Sheets/Excel.
    row_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Tanpa FK ke projects: proyek yang belum ada di D-01 tetap masuk dan ditangkap validator.
    project_id: Mapped[str] = mapped_column(String(20))
    file_name: Mapped[str] = mapped_column(Text)
    sheet_name: Mapped[str | None] = mapped_column(Text)
    # Sel apa adanya. "" = sel kosong, NULL = kolomnya tidak ada di berkas.
    task_code: Mapped[str | None] = mapped_column(Text)
    feature_name: Mapped[str | None] = mapped_column(Text)
    task_name: Mapped[str | None] = mapped_column(Text)
    role_label: Mapped[str | None] = mapped_column(Text)
    pic: Mapped[str | None] = mapped_column(Text)
    complexity_label: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str | None] = mapped_column(Text)
    estimated_days: Mapped[str | None] = mapped_column(Text)
    planned_start: Mapped[str | None] = mapped_column(Text)
    planned_finish: Mapped[str | None] = mapped_column(Text)
    actual_start: Mapped[str | None] = mapped_column(Text)
    actual_finish: Mapped[str | None] = mapped_column(Text)
    status_label: Mapped[str | None] = mapped_column(Text)
    depends_on: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Semua sel dengan nama header asli, termasuk kolom yang tidak dipetakan.
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
