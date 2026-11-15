"""DIG-109: utility hari kerja, tanpa basis data."""

from datetime import date, timedelta

import pytest

from app.modules.data.workdays import (
    count_working_days,
    count_working_days_in_periods,
    finish_date,
    is_working_day,
    merge_periods,
    next_working_day,
    working_days_between,
)

# November 2026: Senin 2, 9, 16, 23, 30. Sabtu-Minggu 7-8, 14-15, 21-22, 28-29.
MON = date(2026, 11, 2)
FRI = date(2026, 11, 6)
SAT = date(2026, 11, 7)
SUN = date(2026, 11, 8)
NEXT_MON = date(2026, 11, 9)


def d(day: int, month: int = 11, year: int = 2026) -> date:
    return date(year, month, day)


def test_weekdays_are_working_days_and_weekends_are_not():
    assert [is_working_day(MON + timedelta(days=i)) for i in range(7)] == [
        True,
        True,
        True,
        True,
        True,
        False,
        False,
    ]


def test_holiday_is_not_a_working_day():
    assert not is_working_day(d(4), {d(4)})


def test_count_is_inclusive_on_both_ends():
    assert count_working_days(MON, MON) == 1
    assert count_working_days(MON, FRI) == 5
    assert count_working_days(MON, NEXT_MON) == 6


def test_weekend_only_range_has_no_working_days():
    assert count_working_days(SAT, SUN) == 0


def test_holidays_reduce_count():
    assert count_working_days(MON, FRI, {d(3), d(5)}) == 3


def test_holiday_on_weekend_is_not_subtracted_twice():
    assert count_working_days(MON, NEXT_MON, {SAT, SUN}) == 6


def test_holidays_outside_range_are_ignored():
    assert count_working_days(MON, FRI, {d(30, 10), d(9)}) == 5


def test_duplicate_holidays_are_counted_once():
    assert count_working_days(MON, FRI, [d(3), d(3)]) == 4


@pytest.mark.parametrize("length", [1, 6, 7, 13, 30, 98, 365, 366])
def test_fast_count_matches_day_by_day_count(length):
    holidays = {d(17, 8), d(25, 12), d(1, 1, 2027), d(26, 12)}
    for offset in range(7):
        start = MON + timedelta(days=offset)
        end = start + timedelta(days=length - 1)
        assert count_working_days(start, end, holidays) == len(
            working_days_between(start, end, holidays)
        )


def test_reversed_range_raises():
    with pytest.raises(ValueError):
        count_working_days(FRI, MON)


def test_next_working_day_skips_weekend_and_holiday():
    assert next_working_day(MON) == MON
    assert next_working_day(SAT) == NEXT_MON
    assert next_working_day(SAT, {NEXT_MON}) == d(10)


def test_finish_date_counts_start_day():
    assert finish_date(MON, 1) == MON
    assert finish_date(MON, 5) == FRI


def test_finish_date_skips_weekend_and_holidays():
    assert finish_date(FRI, 2) == NEXT_MON
    assert finish_date(d(4), 3, {d(5)}) == NEXT_MON


def test_finish_date_starting_on_weekend_begins_next_working_day():
    assert finish_date(SAT, 1) == NEXT_MON


@pytest.mark.parametrize(("days", "expected"), [(0.5, MON), (2.5, d(4)), (3.0, d(4))])
def test_fractional_estimate_rounds_up(days, expected):
    assert finish_date(MON, days) == expected


@pytest.mark.parametrize("days", [0, -1, float("nan"), float("inf")])
def test_finish_date_rejects_invalid_days(days):
    with pytest.raises(ValueError):
        finish_date(MON, days)


def test_finish_date_agrees_with_count():
    holidays = {d(10), d(11)}
    end = finish_date(MON, 8, holidays)
    assert count_working_days(MON, end, holidays) == 8
    assert is_working_day(end, holidays)


def test_merge_overlapping_and_adjacent_periods():
    periods = [(d(10), d(12)), (d(2), d(4)), (d(3), d(6)), (d(13), d(13)), (d(20), d(20))]
    assert merge_periods(periods) == [(d(2), d(6)), (d(10), d(13)), (d(20), d(20))]


def test_merge_contained_period():
    assert merge_periods([(d(2), d(20)), (d(5), d(6))]) == [(d(2), d(20))]


def test_periods_overlap_counted_once():
    # Cuti 2-4 Nov dan izin 3-5 Nov bertumpuk: hari kerja hilang 2, 3, 4, 5 Nov.
    assert count_working_days_in_periods([(d(2), d(4)), (d(3), d(5))]) == 4


def test_periods_clipped_to_window():
    # Cuti 30 Okt - 10 Nov dihitung untuk minggu 2-8 Nov saja.
    assert count_working_days_in_periods([(d(30, 10), d(10))], within=(MON, SUN)) == 5
    assert count_working_days_in_periods([(d(20), d(25))], within=(MON, SUN)) == 0
