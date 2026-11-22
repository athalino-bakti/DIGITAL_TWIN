"""Isi basis data dengan final sources sintetis, untuk staging (DIG-49).

Dari folder backend, dengan DATABASE_URL ke basis data yang sudah `alembic upgrade head`:
    python -m synthetic.load --seed 42 --as-of 2026-11-06

AC DIG-49: data di staging hanya data sintetis. Karena itu perintah ini:
- hanya mengisi basis data yang D-01 sampai D-11-nya masih kosong; `roles` dan
  `complexity_levels` boleh sudah berisi seed migrasi 0005, yang ID-nya sama dan dipertahankan;
- menolak berjalan bila APP_ENV=production;
- mengisi semua tabel dalam satu transaksi: gagal di tengah jalan berarti tidak ada yang masuk.

Data dibangun langsung dari generator (`synthetic.world`), sama persis dengan isi CSV dari
`python -m synthetic` pada seed dan tanggal acuan yang sama.
"""

import argparse
import sys
from datetime import date

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Connection

from synthetic.final_sources import final_source_rows
from synthetic.world import build_world

# Urutan isi mengikuti foreign key.
LOAD_ORDER = (
    "roles",
    "complexity_levels",
    "holidays",
    "projects",
    "resources",
    "tasks",
    "task_dependencies",
    "assignments",
    "workload_items",
    "availability",
    "change_events",
)
# Tabel referensi yang sudah diisi migrasi 0005; baris yang ID-nya sudah ada tidak ditimpa.
SEEDED = {"roles": "role_id", "complexity_levels": "complexity_id"}


class NotEmptyError(Exception):
    pass


def load(connection: Connection, seed: int, as_of: date) -> dict[str, int]:
    """Masukkan final sources sintetis; kembalikan jumlah baris baru per tabel."""
    import app.modules.data.models  # noqa: F401  (mendaftarkan tabel ke metadata)
    from app.db.base import Base

    tables = Base.metadata.tables
    filled = {
        name: connection.scalar(select(func.count()).select_from(tables[name]))
        for name in LOAD_ORDER
        if name not in SEEDED
    }
    filled = {name: count for name, count in filled.items() if count}
    if filled:
        detail = ", ".join(f"{name} {count} baris" for name, count in filled.items())
        raise NotEmptyError(
            f"basis data sudah berisi data ({detail}); hanya untuk basis data kosong"
        )

    rows = final_source_rows(build_world(seed, as_of))
    inserted: dict[str, int] = {}
    for name in LOAD_ORDER:
        table = tables[name]
        batch = rows[name]
        if name in SEEDED:
            key = SEEDED[name]
            present = set(connection.scalars(select(table.c[key])))
            batch = [row for row in batch if row[key] not in present]
        if batch:
            connection.execute(insert(table), batch)
        inserted[name] = len(batch)
    return inserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m synthetic.load", description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 11, 6))
    args = parser.parse_args(argv)

    # Dibaca lewat pengaturan aplikasi (environment, .env, dan SECRETS_DIR), sama seperti API,
    # supaya pengaman ini tetap berlaku walau perintah dijalankan langsung di server.
    from app.core.config import get_settings

    if get_settings().app_env == "production":
        print("ditolak: APP_ENV=production tidak boleh diisi data sintetis", file=sys.stderr)
        return 2

    from app.db.session import engine

    try:
        with engine.begin() as connection:
            inserted = load(connection, args.seed, args.as_of)
    except NotEmptyError as exc:
        print(f"ditolak: {exc}", file=sys.stderr)
        return 1
    total = sum(inserted.values())
    print(f"data sintetis seed {args.seed} per {args.as_of.isoformat()} dimuat: {total} baris")
    for name, count in inserted.items():
        print(f"  {name}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
