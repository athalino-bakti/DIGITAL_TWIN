"""Pembaca tanggal ketat per format sumber (DIG-141), dipakai validator dan normalisasi DIG-130.

Setiap sumber punya satu format sah:
- `ISO` (`YYYY-MM-DD`): CSV final sources (kontrak data bagian 5);
- `PLAN` (`dd/mm/yyyy`): Project Plan hasil ekspor Google Sheets.

Nilai yang tidak persis berformat sumbernya ditolak walaupun bisa ditebak, misalnya
`5 Okt 2026`, `2026/10/05`, `11/9/26`, atau `01/12/2026` di CSV final sources. Pembaca longgar
bisa salah membaca urutan hari dan bulan (PostgreSQL membaca `01/12/2026` sebagai 12 Januari).
"""

import re
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class DateFormat:
    label: str  # untuk pesan, misalnya "YYYY-MM-DD"
    pattern: re.Pattern[str]
    strptime: str


ISO = DateFormat("YYYY-MM-DD", re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"), "%Y-%m-%d")
PLAN = DateFormat("dd/mm/yyyy", re.compile(r"^[0-9]{2}/[0-9]{2}/[0-9]{4}$"), "%d/%m/%Y")


def parse_date(value: str | None, fmt: DateFormat) -> date | None:
    """Tanggal bila `value` persis berformat `fmt` dan tanggalnya ada, selain itu None.

    Pola dicek lebih dulu karena `strptime` sendiri menerima angka satu digit (`1/2/2026`).
    """
    if value is None or not fmt.pattern.fullmatch(value):
        return None
    try:
        return datetime.strptime(value, fmt.strptime).date()
    except ValueError:  # misalnya 2026-02-30
        return None
