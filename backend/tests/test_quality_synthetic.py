"""DIG-144: validator terhadap final sources sintetis J&C (seed 42, as-of 2026-11-06).

Data bersih tidak boleh menghasilkan temuan tolak. Pada data kotor, setiap cacat final sources
di manifest_cacat.csv harus terdeteksi oleh aturan yang dipetakan, dan tidak ada temuan tolak di
luar manifest.
"""

import csv
from pathlib import Path

import pytest

from app.modules.data.quality.rules import CODES, validate_final_sources
from app.modules.data.quality.sources import read_csv_folder
from synthetic.__main__ import main as generate

# Jenis cacat final sources -> nomor aturan. Jenis lain (alias_berbeda, kode_task_hilang) ada di
# sumber mentah dan dicatat di luar cakupan atau diuji di test_quality_staging.py.
RULE_FOR_DEFECT = {
    "wajib_kosong": 1,
    "format_id": 2,
    "enum": 3,
    "fk_tidak_dikenal": 4,
    "duplikat": 5,
    "format_tanggal": 7,
    "urutan_tanggal": 9,
    "siklus_dependency": 12,
}


@pytest.fixture(scope="module")
def generated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("sintetis")
    assert generate(["--out", str(out), "--seed", "42", "--as-of", "2026-11-06", "--dirty"]) == 0
    return out


def expected_defects(folder: Path) -> list[tuple[str, str, str, str]]:
    """(jenis, rule_id, row_key, kolom) untuk setiap cacat final sources di manifest."""
    with (folder / "dirty" / "manifest_cacat.csv").open(encoding="utf-8") as handle:
        manifest = [r for r in csv.DictReader(handle) if r["sumber"] == "final_sources"]
    expected = []
    for row in manifest:
        table = row["berkas"].removesuffix(".csv")
        rule_id = f"DQ-{CODES[table]}-{RULE_FOR_DEFECT[row['jenis']]:03d}"
        key = (
            row["nilai_kotor"] if row["lokasi"] == "baris tambahan" else row["lokasi"].split("=")[1]
        )
        expected.append((row["jenis"], rule_id, key, row["kolom"]))
    return expected


def test_clean_final_sources_have_no_rejections(generated):
    report = validate_final_sources(read_csv_folder(generated / "final_sources"))
    assert [f for f in report.findings if f.level == "tolak"] == []
    assert report.completeness_score() == 1.0


def test_every_final_source_defect_is_detected(generated):
    report = validate_final_sources(read_csv_folder(generated / "dirty" / "final_sources"))
    found = {(f.rule_id, f.row_key): f for f in report.findings}
    expected = expected_defects(generated)
    assert {kind for kind, *_ in expected} == set(RULE_FOR_DEFECT)
    for kind, rule_id, key, column in expected:
        finding = found.get((rule_id, key))
        assert finding is not None, (kind, rule_id, key)
        if column not in ("*", "depends_on_task_id"):
            assert finding.column == column, (kind, rule_id, key)


def test_no_rejection_outside_the_manifest(generated):
    report = validate_final_sources(read_csv_folder(generated / "dirty" / "final_sources"))
    rejected = {(f.rule_id, f.row_key) for f in report.findings if f.level == "tolak"}
    assert rejected == {(rule_id, key) for _, rule_id, key, _ in expected_defects(generated)}


def test_cycle_in_dirty_data_rejects_dep_154(generated):
    report = validate_final_sources(read_csv_folder(generated / "dirty" / "final_sources"))
    closing = [f for f in report.findings if f.rule_id == "DQ-DEP-012"]
    assert [f.row_key for f in closing] == ["DEP-154"]
    members = [f for f in report.findings if f.rule_id == "DQ-DEP-013"]
    assert len(members) == 1 and members[0].level == "peringatan"
