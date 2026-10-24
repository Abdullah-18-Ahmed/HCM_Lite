"""T011: period resolution and working days (contracts/agent-tools.md, spec A-6).

Today is 2026-10-25, a Sunday. "this_*" periods run from the start of the period up to and
including today (period to date); "last_*" periods are the full previous period.
"""

from __future__ import annotations

from datetime import date

import pytest

from hcm_lite.errors import ValidationError
from hcm_lite.models.domain import DateRange
from hcm_lite.services.periods import PERIOD_KEYWORDS, resolve_period, working_days

TODAY = date(2026, 10, 25)


def test_today_is_a_sunday():
    assert TODAY.isoweekday() == 7


@pytest.mark.parametrize(
    ("keyword", "start", "end"),
    [
        ("today", date(2026, 10, 25), date(2026, 10, 25)),
        ("yesterday", date(2026, 10, 24), date(2026, 10, 24)),
        ("this_week", date(2026, 10, 19), date(2026, 10, 25)),
        ("last_week", date(2026, 10, 12), date(2026, 10, 18)),
        ("this_month", date(2026, 10, 1), date(2026, 10, 25)),
        ("last_month", date(2026, 9, 1), date(2026, 9, 30)),
        ("this_quarter", date(2026, 10, 1), date(2026, 10, 25)),
    ],
)
def test_keywords(keyword, start, end):
    r = resolve_period(keyword, today=TODAY)
    assert isinstance(r, DateRange)
    assert (r.start, r.end) == (start, end)
    assert r.label == keyword


def test_keyword_list_matches_contract():
    assert set(PERIOD_KEYWORDS) == {
        "today", "yesterday", "this_week", "last_week", "this_month", "last_month",
        "this_quarter",
    }


def test_keywords_are_case_and_space_tolerant():
    assert resolve_period(" This_Month ", today=TODAY).start == date(2026, 10, 1)


def test_month_boundaries():
    assert resolve_period("yesterday", today=date(2026, 3, 1)).start == date(2026, 2, 28)
    lm = resolve_period("last_month", today=date(2026, 1, 15))
    assert (lm.start, lm.end) == (date(2025, 12, 1), date(2025, 12, 31))
    q = resolve_period("this_quarter", today=date(2026, 5, 20))
    assert (q.start, q.end) == (date(2026, 4, 1), date(2026, 5, 20))
    lw = resolve_period("last_week", today=date(2026, 10, 19))  # a Monday
    assert (lw.start, lw.end) == (date(2026, 10, 12), date(2026, 10, 18))


@pytest.mark.parametrize(
    ("month", "start", "end"),
    [
        ("2026-09", date(2026, 9, 1), date(2026, 9, 30)),
        ("2026-02", date(2026, 2, 1), date(2026, 2, 28)),
        ("2024-02", date(2024, 2, 1), date(2024, 2, 29)),
        ("2026-12", date(2026, 12, 1), date(2026, 12, 31)),
    ],
)
def test_year_month(month, start, end):
    r = resolve_period(month, today=TODAY)
    assert (r.start, r.end, r.label) == (start, end, month)


@pytest.mark.parametrize("bad", ["2026-13", "2026-00", "2026-1", "26-10", "next_week", "", "x"])
def test_unknown_period_rejected(bad):
    with pytest.raises(ValidationError) as exc:
        resolve_period(bad, today=TODAY)
    assert exc.value.field == "period"


def test_default_period_used_when_none():
    assert resolve_period(None, today=TODAY).label == "this_month"
    assert resolve_period(None, today=TODAY, default="today").start == TODAY


def test_iso_range_from_dates_and_strings():
    r = resolve_period(None, today=TODAY, start_date=date(2026, 10, 5), end_date=date(2026, 10, 9))
    assert (r.start, r.end) == (date(2026, 10, 5), date(2026, 10, 9))
    assert r.label == "2026-10-05 to 2026-10-09"
    s = resolve_period(None, today=TODAY, start_date="2026-10-05", end_date="2026-10-09")
    assert (s.start, s.end) == (r.start, r.end)


def test_iso_range_takes_precedence_over_keyword():
    r = resolve_period("today", today=TODAY, start_date="2026-10-05", end_date="2026-10-09")
    assert r.start == date(2026, 10, 5)


def test_single_day_range():
    r = resolve_period(None, today=TODAY, start_date="2026-10-05", end_date="2026-10-05")
    assert r.start == r.end == date(2026, 10, 5)


def test_end_before_start_rejected():
    with pytest.raises(ValidationError) as exc:
        resolve_period(None, today=TODAY, start_date="2026-10-09", end_date="2026-10-05")
    assert exc.value.field == "end_date"


def test_only_one_bound_rejected():
    with pytest.raises(ValidationError) as exc:
        resolve_period(None, today=TODAY, start_date="2026-10-09")
    assert exc.value.field == "end_date"
    with pytest.raises(ValidationError) as exc:
        resolve_period(None, today=TODAY, end_date="2026-10-09")
    assert exc.value.field == "start_date"


def test_malformed_iso_date_rejected():
    with pytest.raises(ValidationError) as exc:
        resolve_period(None, today=TODAY, start_date="2026/10/01", end_date="2026-10-09")
    assert exc.value.field == "start_date"


def test_span_limit_366_days():
    ok = resolve_period(None, today=TODAY, start_date="2025-01-01", end_date="2026-01-01")
    assert (ok.end - ok.start).days + 1 == 366
    with pytest.raises(ValidationError) as exc:
        resolve_period(None, today=TODAY, start_date="2025-01-01", end_date="2026-01-02")
    assert exc.value.field == "end_date"


# --------------------------------------------------------------------------- working days


def test_working_days_excludes_weekends():
    # Mon 2026-10-19 .. Sun 2026-10-25
    assert working_days(date(2026, 10, 19), date(2026, 10, 25)) == 5
    assert working_days(date(2026, 10, 24), date(2026, 10, 25)) == 0  # Sat + Sun
    assert working_days(date(2026, 10, 23), date(2026, 10, 26)) == 2  # Fri + Mon
    assert working_days(date(2026, 10, 1), date(2026, 10, 31)) == 22


def test_working_days_excludes_holidays_on_weekdays_only():
    holidays = {date(2026, 10, 21), date(2026, 10, 24)}  # a Wednesday and a Saturday
    assert working_days(date(2026, 10, 19), date(2026, 10, 25), holidays) == 4
    assert working_days(date(2026, 10, 21), date(2026, 10, 21), holidays) == 0


def test_working_days_single_weekday():
    assert working_days(date(2026, 10, 26), date(2026, 10, 26)) == 1


def test_working_days_for_a_range_object():
    r = resolve_period("this_week", today=TODAY)
    assert working_days(r.start, r.end) == 5


def test_working_days_end_before_start_rejected():
    with pytest.raises(ValidationError):
        working_days(date(2026, 10, 26), date(2026, 10, 25))


@pytest.mark.parametrize("bad", ["1899-12", "2100-01", "0000-01", "９９９９-01", "２０２６-10"])
def test_year_month_out_of_range_or_non_ascii_rejected(bad):
    with pytest.raises(ValidationError):
        resolve_period(bad, today=TODAY)


@pytest.mark.parametrize("ok", ["1900-01", "2099-12"])
def test_year_month_range_bounds_accepted(ok):
    assert resolve_period(ok, today=TODAY).label == ok
