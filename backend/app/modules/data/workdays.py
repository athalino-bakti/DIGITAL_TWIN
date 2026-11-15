"""Perhitungan hari kerja (DIG-107).

Hari kerja adalah Senin sampai Jumat yang tidak tercatat di D-11 holidays. Fungsi
di sini murni (tanpa basis data) supaya bisa dipakai ulang oleh Gantt rencana vs
aktual (DIG-177), CPM (DIG-181), RLI (DIG-187), dan validator ETL, serta mudah
diuji. Pemanggil yang memegang sesi basis data mengambil daftar libur lewat
`service.holiday_dates`.

Semua rentang tanggal bersifat inklusif di kedua ujung, mengikuti cara D-09
availability menyimpan `date_start` dan `date_end`.
"""

import math
from collections.abc import Collection, Iterable, Iterator
from datetime import date, timedelta

ONE_DAY = timedelta(days=1)
# date.weekday(): Senin 0 sampai Minggu 6.
SATURDAY = 5


def is_weekend(day: date) -> bool:
    return day.weekday() >= SATURDAY


def is_working_day(day: date, holidays: Collection[date] = ()) -> bool:
    return not is_weekend(day) and day not in holidays


def _check_range(start: date, end: date) -> None:
    if end < start:
        raise ValueError(f"Tanggal akhir {end} lebih awal dari tanggal awal {start}")


def iter_days(start: date, end: date) -> Iterator[date]:
    _check_range(start, end)
    day = start
    while day <= end:
        yield day
        day += ONE_DAY


def working_days_between(start: date, end: date, holidays: Collection[date] = ()) -> list[date]:
    """Daftar hari kerja dari `start` sampai `end` (inklusif)."""
    return [day for day in iter_days(start, end) if is_working_day(day, holidays)]


def count_working_days(start: date, end: date, holidays: Collection[date] = ()) -> int:
    """Jumlah hari kerja dari `start` sampai `end` (inklusif).

    Dihitung per minggu penuh lalu sisa hari, sehingga rentang panjang (misalnya
    cuti melahirkan) tidak perlu diulang hari demi hari.
    """
    _check_range(start, end)
    total_days = (end - start).days + 1
    full_weeks, remainder = divmod(total_days, 7)
    count = full_weeks * 5
    day = start + timedelta(weeks=full_weeks)
    for _ in range(remainder):
        if not is_weekend(day):
            count += 1
        day += ONE_DAY
    # Libur yang jatuh pada akhir pekan tidak mengurangi dua kali.
    count -= sum(
        1 for holiday in set(holidays) if start <= holiday <= end and not is_weekend(holiday)
    )
    return count


def next_working_day(day: date, holidays: Collection[date] = ()) -> date:
    """`day` itu sendiri bila hari kerja, atau hari kerja pertama sesudahnya."""
    while not is_working_day(day, holidays):
        day += ONE_DAY
    return day


def finish_date(start: date, working_days: float, holidays: Collection[date] = ()) -> date:
    """Tanggal selesai task yang mulai `start` dan butuh `working_days` hari kerja.

    Hari mulai ikut dihitung (task 1 hari yang mulai Senin selesai Senin). Bila
    `start` jatuh pada akhir pekan atau libur, pekerjaan baru dimulai hari kerja
    berikutnya. Estimasi pecahan seperti 0,5 atau 2,5 hari dibulatkan ke atas
    karena sisa setengah hari tetap memakai satu hari kalender.
    """
    if working_days <= 0 or not math.isfinite(working_days):
        raise ValueError("Jumlah hari kerja harus lebih dari 0")
    remaining = math.ceil(working_days)
    day = next_working_day(start, holidays)
    remaining -= 1
    while remaining:
        day = next_working_day(day + ONE_DAY, holidays)
        remaining -= 1
    return day


def merge_periods(periods: Iterable[tuple[date, date]]) -> list[tuple[date, date]]:
    """Gabungkan periode yang bertumpuk atau bersambung menjadi periode tunggal.

    Dipakai sebelum menghitung hari kerja yang hilang dari beberapa catatan
    ketidakhadiran milik satu anggota, supaya hari yang sama tidak terhitung dua kali.
    """
    merged: list[tuple[date, date]] = []
    for start, end in sorted(periods):
        _check_range(start, end)
        if merged and start <= merged[-1][1] + ONE_DAY:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def count_working_days_in_periods(
    periods: Iterable[tuple[date, date]],
    holidays: Collection[date] = (),
    within: tuple[date, date] | None = None,
) -> int:
    """Jumlah hari kerja yang tercakup sedikitnya satu periode.

    `within` membatasi hitungan ke satu jendela, misalnya satu minggu RLI atau satu
    bulan kalender.
    """
    total = 0
    for start, end in merge_periods(periods):
        if within is not None:
            start, end = max(start, within[0]), min(end, within[1])
            if end < start:
                continue
        total += count_working_days(start, end, holidays)
    return total
