"""Tabel pendukung J&C yang dibaca tWinner (DATA_CONTRACT bagian 7.1 dan 7.3).

Bukan bagian Data Dictionary D-01 s.d. D-11 dan bukan tabel internal J&C (7.2). Kolomnya
mengikuti bagian 7.3 apa adanya: perubahan kolom di sini juga mengubah kontrak dengan tWinner
dan harus lewat prosedur bagian 9.

`resource_skills` (DIG-220) mencatat tingkat penguasaan anggota per peran, termasuk peran
rangkap dan lintas peran. Keahlian hanya atribut anggota, sehingga ikut terhapus bersama
anggotanya. Peran tidak bisa dihapus selama masih dipakai.
"""

from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PROFICIENCY_MIN = 1  # dasar, masih membutuhkan pendampingan
PROFICIENCY_MAX = 3  # mahir, dapat mengambil alih task dan membimbing anggota lain


class ResourceSkill(Base):
    __tablename__ = "resource_skills"
    __table_args__ = (
        CheckConstraint(
            f"proficiency_level BETWEEN {PROFICIENCY_MIN} AND {PROFICIENCY_MAX}",
            name="proficiency_level_range",
        ),
    )

    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.resource_id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[str] = mapped_column(
        ForeignKey("roles.role_id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    proficiency_level: Mapped[int] = mapped_column(SmallInteger)
    assessed_date: Mapped[date] = mapped_column(Date)
