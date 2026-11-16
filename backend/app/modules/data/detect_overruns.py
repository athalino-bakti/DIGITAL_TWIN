"""Deteksi overrun otomatis dari terminal atau scheduler (DIG-154).

Dari folder backend:
    python -m app.modules.data.detect_overruns
    python -m app.modules.data.detect_overruns --dry-run
    python -m app.modules.data.detect_overruns --as-of 2026-11-16

Membuat kejadian overrun (D-10) untuk task yang lewat planned_finish, belum selesai, dan
belum punya kejadian overrun. Aman dijalankan berulang, misalnya sekali sehari.
"""

import argparse
import sys
from datetime import date

# Semua model harus terdaftar di metadata saat CLI ini jalan sendiri tanpa app.main.
import app.modules.auth.models  # noqa: F401
from app.db.session import SessionLocal
from app.modules.data.my_task_service import detect_overruns


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deteksi task yang melewati rencana (overrun)")
    parser.add_argument("--as-of", default=None, help="Tanggal acuan YYYY-MM-DD, bawaan hari ini")
    parser.add_argument("--dry-run", action="store_true", help="Hanya menghitung, tidak menyimpan")
    args = parser.parse_args(argv)
    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    except ValueError:
        print("--as-of harus berformat YYYY-MM-DD", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        outcome = detect_overruns(db, as_of, args.dry_run)
    verb = "akan dibuat (dry run)" if outcome.dry_run else "dibuat"
    print(f"{outcome.created_count} kejadian overrun {verb} per {as_of.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
