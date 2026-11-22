"""DIG-144: katalog docs/DATA_QUALITY_RULES.md sama dengan registry aturan di kode."""

from pathlib import Path

from app.modules.data.quality.run import ALL_RULES

CATALOG = Path(__file__).resolve().parents[2] / "docs" / "DATA_QUALITY_RULES.md"


def catalog_rows() -> dict[str, list[str]]:
    rows = {}
    for line in CATALOG.read_text(encoding="utf-8").splitlines():
        if line.startswith("| DQ-"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows[cells[0]] = cells
    return rows


def test_every_rule_is_in_the_catalog_and_back():
    assert set(catalog_rows()) == set(ALL_RULES)


def test_catalog_characteristic_and_level_match_the_code():
    for rule_id, cells in catalog_rows().items():
        rule = ALL_RULES[rule_id]
        assert (cells[3], cells[4]) == (rule.characteristic, rule.level), rule_id
