"""Format sel CSV bersama: laporan kualitas (DIG-148), ekspor final sources (DIG-193), dan
generator data sintetis (DIG-81)."""

from datetime import date

# Awalan yang membuat Excel/Sheets membaca sel sebagai formula (CSV/formula injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Sel teks yang bisa terbaca sebagai formula diawali `'`; angka dibiarkan."""
    if isinstance(value, str) and value.startswith(_FORMULA_START):
        return "'" + value
    return value


def format_value(value: object) -> str:
    """Nilai final sources seperti di Data Dictionary: tanggal ISO, boolean huruf kecil."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        # repr = representasi terpendek yang dibaca balik persis; :g memotong ke 6 digit.
        return repr(value) if value != int(value) else f"{value:.1f}"
    return str(value)
