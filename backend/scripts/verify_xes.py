"""Verifikasi ekspor XES dengan pm4py (DIG-174, story DIG-39).

pm4py sengaja bukan dependensi proyek. Skrip ini punya dua langkah yang dijalankan di venv berbeda.

1. `export` di venv proyek (folder backend, DATABASE_URL ke basis data berisi data sintetis):

       python -m synthetic.load --seed 42 --as-of 2026-11-06
       python -m synthetic --out synthetic-output --seed 42 --as-of 2026-11-06
       python -m scripts.verify_xes export --out synthetic-output/xes/event_log.xes \
           --trello-json synthetic-output/raw/trello/trello_board.json

   `--trello-json` mengisi staging Trello dari ekspor papan sintetis lalu membentuk ulang
   event_log. Hasilnya `event_log.xes` dan `event_log.counts.json` (jumlah dari tabel).

2. `check` di venv sementara yang hanya berisi pm4py:

       python -m venv %TEMP%\\pm4v
       %TEMP%\\pm4v\\Scripts\\pip install pm4py
       %TEMP%\\pm4v\\Scripts\\python -m scripts.verify_xes check synthetic-output/xes/event_log.xes

   Pakai path venv yang pendek: di Windows, path panjang membuat pemasangan pm4py terpotong
   (batas 260 karakter) dan `import pm4py` gagal. Set `PYTHONIOENCODING=utf-8` bila banner
   pm4py gagal tercetak di konsol.

   Membaca berkas dengan `pm4py.read_xes`, mencocokkan jumlah trace, event, dan aktivitas dengan
   `counts.json`, lalu menjalankan `pm4py.discover_dfg`. Kode keluar 0 bila semua cocok.
"""

import argparse
import json
import sys
from pathlib import Path


def export(out: Path, trello_json: Path | None) -> int:
    from app.db.session import SessionLocal
    from app.modules.data.event_log import rebuild_event_log, xes_events
    from app.modules.data.xes import serialize

    with SessionLocal() as db:
        if trello_json is not None:
            from app.integrations.trello.parser import parse_board_export
            from app.modules.data.trello_staging import save_trello_import

            board = json.loads(trello_json.read_text(encoding="utf-8"))
            saved = save_trello_import(db, parse_board_export(board), None)
            db.commit()
            print(f"staging Trello: {saved.inserted} action baru")
            report = rebuild_event_log(db)
            db.commit()
            print(f"event_log dibentuk ulang: {report.events} event, {report.cases} case")
        events = xes_events(db)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in serialize(events):
            handle.write(chunk)
    counts = {
        "traces": len({e.case_id for e in events}),
        "events": len(events),
        "activities": len({e.activity for e in events}),
    }
    out.with_suffix(".counts.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(f"{out}: {counts}")
    return 0


def check(path: Path) -> int:
    import pm4py

    expected = json.loads(path.with_suffix(".counts.json").read_text())
    log = pm4py.read_xes(str(path))
    actual = {
        "traces": int(log["case:concept:name"].nunique()),
        "events": len(log),
        "activities": int(log["concept:name"].nunique()),
    }
    dfg, starts, ends = pm4py.discover_dfg(log)
    print(f"pm4py {pm4py.__version__}")
    print(f"dari tabel event_log : {expected}")
    print(f"dibaca pm4py         : {actual}")
    print(f"DFG: {len(dfg)} relasi, {len(starts)} aktivitas awal, {len(ends)} aktivitas akhir")
    for (source, target), frequency in sorted(dfg.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {source} -> {target}: {frequency}")
    ok = actual == expected and len(dfg) > 0
    print("HASIL:", "COCOK" if ok else "TIDAK COCOK")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    export_cmd = sub.add_parser("export", help="tulis XES dari event_log (venv proyek)")
    export_cmd.add_argument("--out", type=Path, required=True)
    export_cmd.add_argument("--trello-json", type=Path)
    check_cmd = sub.add_parser("check", help="baca XES dengan pm4py (venv pm4py)")
    check_cmd.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    if args.command == "export":
        return export(args.out, args.trello_json)
    return check(args.path)


if __name__ == "__main__":
    sys.exit(main())
