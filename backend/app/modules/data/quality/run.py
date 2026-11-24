"""CLI validator kualitas data (DIG-31), sementara sampai endpoint DIG-146 ada.

Dari folder backend:

    python -m app.modules.data.quality.run --final-sources <folder> --as-of 2026-11-06
    python -m app.modules.data.quality.run --workbook <berkas.xlsx> --out <folder>
    python -m app.modules.data.quality.run --database --trello --currentness --as-of 2026-11-06

Mencetak ringkasan per aturan, skor completeness, dan currentness. `--out` menulis
temuan.csv, ringkasan.csv, baris_ditolak.csv, kelengkapan.csv, dan currentness.csv.
Validator hanya membaca; basis data dipakai lewat DATABASE_URL tanpa ditulis.
"""

import argparse
import csv
import sys
from dataclasses import asdict, fields
from datetime import date
from pathlib import Path

from app.modules.data.quality import currentness, rules, staging
from app.modules.data.quality.engine import RULES, Finding, Report, RuleSummary
from app.modules.data.quality.sources import read_csv_folder, read_database, read_workbook

ALL_RULES = RULES  # semua modul aturan sudah diimpor di atas


def merge(reports: list[Report]) -> Report:
    merged = Report(",".join(r.source for r in reports))
    for report in reports:
        merged.findings += report.findings
        merged.summaries += report.summaries
        merged.completeness.update(report.completeness)
        merged.currentness += report.currentness
    return merged


def write_outputs(report: Report, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)

    def write(name: str, header: list[str], rows: list[dict]) -> None:
        with (folder / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, header, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    write("temuan.csv", [f.name for f in fields(Finding)], [asdict(f) for f in report.findings])
    write(
        "ringkasan.csv",
        [f.name for f in fields(RuleSummary)],
        [asdict(s) for s in report.summaries],
    )
    rejected = [
        {**row, "rule_ids": ";".join(row["rule_ids"]), "reasons": " | ".join(row["reasons"])}
        for row in report.rejected_rows()
    ]
    write(
        "baris_ditolak.csv",
        ["source", "table", "row_number", "row_key", "rule_ids", "reasons"],
        rejected,
    )
    write(
        "kelengkapan.csv",
        ["table", "filled", "total", "score"],
        [
            {"table": t, "filled": f, "total": n, "score": f"{f / n:.4f}" if n else ""}
            for t, (f, n) in report.completeness.items()
        ],
    )
    if report.currentness:
        write("currentness.csv", list(report.currentness[0]), report.currentness)


def print_report(report: Report) -> None:
    print(f"{'rule_id':<12} {'tingkat':<10} {'langgar':>7} {'periksa':>7}  aturan")
    for summary in sorted(report.summaries, key=lambda s: (s.source, s.rule_id)):
        if summary.violated:
            print(
                f"{summary.rule_id:<12} {summary.level:<10} {summary.violated:>7} "
                f"{summary.checked:>7}  {summary.text}"
            )
    if report.completeness:
        print("\nCompleteness (sel wajib terisi / seluruh sel wajib):")
        for table, (filled, total) in report.completeness.items():
            print(f"  {table:<18} {filled}/{total}")
        print(f"  {'keseluruhan':<18} {report.completeness_score():.4%}")
    if report.currentness:
        print("\nCurrentness:")
        for row in report.currentness:
            print(
                f"  {row['source']:<13} impor terakhir {row['last_success_at']}, "
                f"umur impor {row['import_age_days']} hari, "
                f"aksi terbaru {row['newest_source_at']}, selisih {row['source_lag_days']} hari"
            )
    tolak = [f for f in report.findings if f.level == "tolak"]
    print(
        f"\nTemuan: {len(tolak)} tolak ({len(report.rejected_rows())} baris ditolak), "
        f"{len(report.findings) - len(tolak)} peringatan"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--final-sources", type=Path, help="folder berisi <tabel>.csv")
    target.add_argument("--workbook", type=Path, help="workbook dengan sheet per tabel")
    target.add_argument("--database", action="store_true", help="tabel final sources di DB")
    parser.add_argument("--trello", action="store_true", help="periksa staging Trello di DB")
    parser.add_argument("--currentness", action="store_true", help="currentness dari import_job")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    parser.add_argument("--source", help="nama sumber pada temuan (bawaan: jenis sasaran)")
    parser.add_argument("--out", type=Path, help="folder keluaran CSV")
    args = parser.parse_args(argv)
    if not (
        args.final_sources or args.workbook or args.database or args.trello or args.currentness
    ):
        parser.error("pilih minimal satu sasaran")

    reports = []
    if args.final_sources:
        tables = read_csv_folder(args.final_sources)
        reports.append(rules.validate_final_sources(tables, args.source or "final_sources_csv"))
    if args.workbook:
        tables = read_workbook(args.workbook)
        reports.append(
            rules.validate_final_sources(tables, args.source or "final_sources_workbook")
        )
    if args.database or args.trello or args.currentness:
        from app.db.session import SessionLocal

        with SessionLocal() as db:
            if args.database:
                reports.append(rules.validate_final_sources(read_database(db), "final_sources_db"))
            if args.trello:
                reports.append(staging.validate_trello(staging.read_trello_cards(db)))
            if args.currentness:
                reports.append(currentness.currentness_report(db, args.as_of))

    report = merge(reports)
    print_report(report)
    if args.out:
        write_outputs(report, args.out)
        print(f"Keluaran ditulis ke {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
