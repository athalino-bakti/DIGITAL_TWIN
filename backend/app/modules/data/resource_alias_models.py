"""Alias identitas anggota antar tool (DIG-110), tabel internal J&C (DATA_CONTRACT 7.2).

Satu baris memetakan satu identitas di satu sumber ke satu `resource_id`. Satu anggota boleh
punya banyak alias (misalnya dua akun Trello atau beberapa varian nama PIC), tetapi satu alias
hanya menunjuk satu anggota: unik pada (`source`, `alias_key`).

`alias` adalah nilai asli untuk ditampilkan, `alias_key` nilai ternormalisasi untuk pencocokan
(lihat `app.modules.data.resource_alias_service.alias_key`). Kuncinya per sumber:
- trello: id member (24 heksadesimal), karena username bisa diganti. Username dan nama lengkap
  hanya keterangan di `username` dan `display_name`;
- teamgit: email author commit; nama author di `display_name`;
- project_plan: nama PIC. Varian nama sengaja menjadi alias terpisah yang dipetakan manual.

Alias adalah atribut anggota, sehingga ikut terhapus bersama anggotanya; identitasnya lalu
muncul lagi di daftar belum terpetakan. `mapped_by_user_id` mencatat akun aplikasi yang terakhir
membuat atau mengubah pemetaan, sebagai jejak *traceability* ISO/IEC 25012.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.data.enums import IdentitySource
from app.modules.data.models import matches, one_of
from app.modules.data.staging_models import TRELLO_ID_PATTERN


class ResourceAlias(Base):
    __tablename__ = "resource_alias"
    __table_args__ = (
        CheckConstraint(one_of("source", IdentitySource), name="source_valid"),
        CheckConstraint(
            f"source <> '{IdentitySource.TRELLO}' OR {matches('alias_key', TRELLO_ID_PATTERN)}",
            name="trello_id_format",
        ),
        CheckConstraint("alias_key <> ''", name="alias_key_not_empty"),
        UniqueConstraint("source", "alias_key"),
    )

    alias_id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    resource_id: Mapped[str] = mapped_column(
        ForeignKey("resources.resource_id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(20))
    alias: Mapped[str] = mapped_column(String(200))
    alias_key: Mapped[str] = mapped_column(String(200))
    username: Mapped[str | None] = mapped_column(String(100))
    display_name: Mapped[str | None] = mapped_column(String(200))
    mapped_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.user_id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
