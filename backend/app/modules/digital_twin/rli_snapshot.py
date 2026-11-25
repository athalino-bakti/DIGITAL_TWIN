"""Snapshot RLI untuk dibaca tWinner lewat view `resource_load_index` (DIG-192, story DIG-44).

Formula RLI hanya ada di Python (`rli.py`, DIG-187). Snapshot menyimpan hasil heatmap yang
sama dengan endpoint DIG-188, sehingga tWinner dan tab Beban Resource membaca angka yang sama.
Setiap refresh mengganti seluruh isi snapshot.

Dari folder backend:
    python -m app.modules.digital_twin.rli_snapshot              # as-of hari ini
    python -m app.modules.digital_twin.rli_snapshot --as-of 2026-11-06
"""

import argparse
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    delete,
    func,
    insert,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base
from app.db.session import SessionLocal
from app.modules.digital_twin.heatmap_service import MAX_WEEKS, build_heatmap, default_start


class RliSnapshot(Base):
    """Tabel internal J&C (DATA_CONTRACT bagian 7.1); tWinner membaca view-nya."""

    __tablename__ = "rli_snapshot"

    resource_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("resources.resource_id", ondelete="CASCADE"), primary_key=True
    )
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    rli: Mapped[Decimal | None] = mapped_column(Numeric(8, 3))
    category: Mapped[str] = mapped_column(String(20))
    project_load: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    non_project_load: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    capacity: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    available_days: Mapped[int] = mapped_column(Integer)
    onboarding_factor: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    tasks: Mapped[int] = mapped_column(Integer)
    workload_items: Mapped[int] = mapped_column(Integer)
    formula_version: Mapped[str] = mapped_column(String(30))
    provisional: Mapped[bool] = mapped_column(Boolean)
    as_of: Mapped[date] = mapped_column(Date)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


def refresh(db: Session, as_of: date) -> int:
    """Hitung ulang RLI semua anggota untuk 26 minggu mulai 4 minggu sebelum `as_of`."""
    heatmap = build_heatmap(db, default_start(as_of), MAX_WEEKS, as_of)
    rows = [
        cell.model_dump()
        | {
            "resource_id": row.resource_id,
            "formula_version": heatmap.formula_version,
            "provisional": heatmap.provisional,
            "as_of": as_of,
        }
        for row in heatmap.rows
        for cell in row.cells
    ]
    # DELETE, bukan TRUNCATE: jc_app hanya diberi SELECT/INSERT/UPDATE/DELETE (migrasi 0014,
    # docs/DATABASE_ROLES.md, tes test_jc_app_cannot_truncate).
    db.execute(delete(RliSnapshot))
    if rows:
        db.execute(insert(RliSnapshot), rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Isi ulang snapshot RLI (DIG-192)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    with SessionLocal() as db:
        count = refresh(db, args.as_of)
        db.commit()
    print(f"rli_snapshot: {count} baris, as-of {args.as_of}")


if __name__ == "__main__":
    main()
