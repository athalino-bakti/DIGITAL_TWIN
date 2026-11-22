"""DIG-111: normalisasi alias identitas per sumber, tanpa basis data."""

import pytest

from app.modules.data.enums import IdentitySource
from app.modules.data.resource_alias_service import alias_key
from synthetic.dirty import _pic_variants


def test_trello_key_is_lowercase_member_id():
    assert alias_key("trello", "  ABCDEF0123456789ABCDEF01 ") == "abcdef0123456789abcdef01"


@pytest.mark.parametrize("value", ["saripusp", "f" * 23, "f" * 25, "g" * 24, ""])
def test_trello_key_must_be_24_hex(value):
    with pytest.raises(ValueError, match="24 karakter heksadesimal"):
        alias_key(IdentitySource.TRELLO, value)


def test_teamgit_key_is_trimmed_lowercase_email():
    assert alias_key("teamgit", "  Sari.Puspitasari@J-C.Example ") == "sari.puspitasari@j-c.example"


def test_project_plan_key_ignores_case_and_extra_spaces():
    assert alias_key("project_plan", "  SARI   Puspitasari ") == "sari puspitasari"


def test_project_plan_variants_stay_separate_aliases():
    """Varian nama PIC dari data kotor tidak dicocokkan otomatis; masing-masing dipetakan
    manual. Hanya varian yang berbeda huruf besar-kecil yang jatuh ke kunci yang sama."""
    keys = {alias_key("project_plan", v) for v in _pic_variants("Sari Puspitasari")}
    assert keys == {"sari", "sari puspitasari", "sari p"}
