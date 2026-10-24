"""Period resolution and working-day counting (contracts/agent-tools.md, spec A-6/A-7).

Periods resolve against an injected ``today`` (the app time zone's date), never the system clock.
Weeks start on Monday. ``this_week`` / ``this_month`` / ``this_quarter`` run from the start of
the period up to and including ``today`` (period to date); ``last_*`` cover the full previous
period; ``YYYY-MM`` covers the full calendar month.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Iterable
from datetime import date, timedelta

from hcm_lite.errors import ValidationError
from hcm_lite.models.domain import PERIOD_KEYWORDS, YEAR_MONTH_PATTERN, DateRange

__all__ = ["MAX_SPAN_DAYS", "PERIOD_KEYWORDS", "resolve_period", "working_days"]

MAX_SPAN_DAYS = 366
_YEAR_MONTH = re.compile(YEAR_MONTH_PATTERN)


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _keyword_range(keyword: str, today: date) -> tuple[date, date]:
    if keyword == "today":
        return today, today
    if keyword == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    monday = today - timedelta(days=today.weekday())
    if keyword == "this_week":
        return monday, today
    if keyword == "last_week":
        return monday - timedelta(days=7), monday - timedelta(days=1)
    if keyword == "this_month":
        return today.replace(day=1), today
    if keyword == "last_month":
        last_day_prev = today.replace(day=1) - timedelta(days=1)
        return _month_range(last_day_prev.year, last_day_prev.month)
    if keyword == "this_quarter":
        first_month = 3 * ((today.month - 1) // 3) + 1
        return date(today.year, first_month, 1), today
    raise AssertionError(keyword)  # unreachable: callers check PERIOD_KEYWORDS


def _as_date(value: date | str, field: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        raise ValidationError(field, "must be an ISO date (YYYY-MM-DD)") from None


def resolve_period(
    period: str | None = None,
    *,
    today: date,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    default: str = "this_month",
) -> DateRange:
    """Resolve a keyword, ``YYYY-MM`` or an ISO ``start_date``/``end_date`` pair to a range.

    Explicit dates take precedence over ``period``. Raises ``ValidationError`` for an unknown
    period, a single bound, ``end < start`` or a span over 366 days.
    """
    if start_date is not None or end_date is not None:
        if start_date is None:
            raise ValidationError("start_date", "is required with end_date")
        if end_date is None:
            raise ValidationError("end_date", "is required with start_date")
        start, end = _as_date(start_date, "start_date"), _as_date(end_date, "end_date")
        if end < start:
            raise ValidationError("end_date", "must be on or after start_date")
        if (end - start).days + 1 > MAX_SPAN_DAYS:
            raise ValidationError("end_date", f"the range may span at most {MAX_SPAN_DAYS} days")
        return DateRange(start=start, end=end, label=f"{start.isoformat()} to {end.isoformat()}")

    keyword = (period if period is not None else default).strip().lower()
    if keyword in PERIOD_KEYWORDS:
        start, end = _keyword_range(keyword, today)
        return DateRange(start=start, end=end, label=keyword)
    if _YEAR_MONTH.match(keyword):
        year, month = (int(p) for p in keyword.split("-"))
        start, end = _month_range(year, month)
        return DateRange(start=start, end=end, label=keyword)
    raise ValidationError("period", f"must be one of {', '.join(PERIOD_KEYWORDS)} or YYYY-MM")


def working_days(start: date, end: date, holidays: Iterable[date] = ()) -> int:
    """Count Monday–Friday dates in ``[start, end]`` that are not listed holidays."""
    if end < start:
        raise ValidationError("end_date", "must be on or after start_date")
    holiday_set = set(holidays)
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5 and day not in holiday_set:
            count += 1
        day += timedelta(days=1)
    return count
