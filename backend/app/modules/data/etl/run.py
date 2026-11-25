"""Jalankan ETL staging ke tabel final dari terminal (DIG-134).

Dari folder backend, dengan DATABASE_URL:
    python -m app.modules.data.etl.run --project PRJ-001
    python -m app.modules.data.etl.run --all

Satu transaksi untuk semua proyek: gagal di tengah berarti tidak ada yang tersimpan.
Kode keluar 0 berhasil, 1 bila tidak ada batch Project Plan untuk proyek yang diminta.
"""

import argparse
import json
import sys

from app.modules.data.etl.load import run


def main(argv: list[str] | None = None, session_factory=None) -> int:
    parser = argparse.ArgumentParser(description="ETL staging ke D-05, D-06, D-07 (DIG-29)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--project", help="project_id, misalnya PRJ-001")
    group.add_argument("--all", action="store_true", help="semua proyek yang punya batch")
    args = parser.parse_args(argv)
    if session_factory is None:
        from app.db.session import SessionLocal as session_factory

    with session_factory() as db:
        reports = run(db, None if args.all else args.project)
        db.commit()
    for report in reports:
        print(json.dumps(report.as_dict(), ensure_ascii=False, default=str))
    return 0 if all(r.job_id is not None for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
