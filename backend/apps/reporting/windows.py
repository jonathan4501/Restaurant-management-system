"""
Business-date windows: the one place that turns "which day" into "which timestamps".

A restaurant's day runs past midnight, so 02:30 belongs to yesterday's service. `apps.core.business_date`
answers that for a single instant; a report needs the inverse — the timestamp window whose instants map
to a given business date — and the window for a range of dates.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone as dj_timezone

from apps.accounts.models import Restaurant
from apps.core.business_date import business_date

DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 92


def restaurant_zone(restaurant: Restaurant) -> ZoneInfo:
    return ZoneInfo(restaurant.timezone)


def current_business_date(restaurant: Restaurant, at: datetime | None = None) -> date:
    return business_date(at or dj_timezone.now(), restaurant.timezone, restaurant.day_cutover_hour)


def day_bounds(restaurant: Restaurant, day: date) -> tuple[datetime, datetime]:
    """[start, end) — cutover hour to cutover hour, in the restaurant's own zone."""
    start_local = datetime.combine(
        day, datetime.min.time(), tzinfo=restaurant_zone(restaurant)
    ) + timedelta(hours=restaurant.day_cutover_hour)
    return start_local, start_local + timedelta(days=1)


def window_bounds(restaurant: Restaurant, start_day: date, end_day: date) -> tuple[datetime, datetime]:
    """[start, end) covering both business dates and every date between them."""
    start, _ = day_bounds(restaurant, start_day)
    _, end = day_bounds(restaurant, end_day)
    return start, end


def business_dates(start_day: date, end_day: date) -> list[date]:
    span = (end_day - start_day).days
    return [start_day + timedelta(days=offset) for offset in range(span + 1)]


def resolve_window(
    restaurant: Restaurant,
    from_day: date | None = None,
    to_day: date | None = None,
    *,
    days: int = DEFAULT_WINDOW_DAYS,
) -> tuple[date, date]:
    """
    Fill in whichever end the caller left out. Defaults to the last `days` business dates ending
    today, and clamps the span so one query cannot walk the whole event log.
    """
    end = to_day or current_business_date(restaurant)
    start = from_day or end - timedelta(days=days - 1)
    if start > end:
        start, end = end, start
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        start = end - timedelta(days=MAX_WINDOW_DAYS - 1)
    return start, end
