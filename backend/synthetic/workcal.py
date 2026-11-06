"""Kalender hari kerja: akhir pekan, hari libur, masa aktif, dan ketidakhadiran anggota."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Absence:
    resource_id: str
    start: date
    end: date
    absence_type: str
    known_at_planning: bool

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


class WorkCalendar:
    """Menghitung hari kerja per anggota.

    Mode "plan" hanya mengenal ketidakhadiran yang sudah diketahui saat sprint planning.
    Mode "actual" mengenal semua ketidakhadiran, termasuk cuti mendadak dan rotasi.
    """

    def __init__(self, holidays: Iterable[date]):
        self.holidays = set(holidays)
        self.join_dates: dict[str, date] = {}
        self.absences: dict[str, list[Absence]] = {}

    def add_resource(self, resource_id: str, join_date: date) -> None:
        self.join_dates[resource_id] = join_date
        self.absences.setdefault(resource_id, [])

    def add_absence(self, absence: Absence) -> None:
        self.absences.setdefault(absence.resource_id, []).append(absence)

    def is_workday(self, day: date, resource_id: str | None = None, mode: str = "plan") -> bool:
        if day.weekday() >= 5 or day in self.holidays:
            return False
        if resource_id is None:
            return True
        if day < self.join_dates[resource_id]:
            return False
        for absence in self.absences.get(resource_id, []):
            if absence.absence_type == "rotation_in":
                continue
            if (mode == "actual" or absence.known_at_planning) and absence.covers(day):
                return False
        return True

    def first_workday(self, day: date, resource_id: str | None = None, mode: str = "plan") -> date:
        while not self.is_workday(day, resource_id, mode):
            day += timedelta(days=1)
        return day

    def next_workday(self, day: date, resource_id: str | None = None, mode: str = "plan") -> date:
        return self.first_workday(day + timedelta(days=1), resource_id, mode)

    def add_workdays(
        self, start: date, days: int, resource_id: str | None = None, mode: str = "plan"
    ) -> date:
        """Tanggal hari kerja ke-`days` dengan `start` dihitung sebagai hari pertama."""
        day = self.first_workday(start, resource_id, mode)
        for _ in range(max(days, 1) - 1):
            day = self.next_workday(day, resource_id, mode)
        return day

    def previous_workday(
        self, day: date, resource_id: str | None = None, mode: str = "plan"
    ) -> date:
        day -= timedelta(days=1)
        while not self.is_workday(day, resource_id, mode):
            day -= timedelta(days=1)
        return day

    def count_workdays(
        self, start: date, end: date, resource_id: str | None = None, mode: str = "plan"
    ) -> int:
        """Jumlah hari kerja pada rentang [start, end]."""
        count, day = 0, start
        while day <= end:
            if self.is_workday(day, resource_id, mode):
                count += 1
            day += timedelta(days=1)
        return count

    def absent_on(self, resource_id: str, day: date) -> Absence | None:
        for absence in self.absences.get(resource_id, []):
            if absence.absence_type != "rotation_in" and absence.covers(day):
                return absence
        return None
