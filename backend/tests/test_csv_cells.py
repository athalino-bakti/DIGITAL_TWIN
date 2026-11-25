"""DIG-193: format nilai CSV final sources tanpa kehilangan presisi."""

from datetime import date

from app.modules.data.csv_cells import format_value


def test_float_keeps_full_precision():
    # `:g` dulu memberi 2.33333 dan 1.23457e+06.
    assert format_value(2.3333333333) == "2.3333333333"
    assert format_value(1234567.5) == "1234567.5"
    assert float(format_value(0.1 + 0.2)) == 0.1 + 0.2


def test_dataset_shapes_are_unchanged():
    assert [format_value(v) for v in (2.5, 0.3, 1.0, 3.0)] == ["2.5", "0.3", "1.0", "3.0"]
    assert format_value(None) == ""
    assert format_value(True) == "true"
    assert format_value(date(2026, 11, 25)) == "2026-11-25"
