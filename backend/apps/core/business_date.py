"""
A restaurant's day runs past midnight. An order at 01:30 belongs to yesterday's service.

business_date = local time shifted back by the cutover hour, then the calendar date.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def business_date(at: datetime, timezone: str, cutover_hour: int) -> date:
    if at.tzinfo is None:
        raise ValueError("business_date needs an aware datetime")
    if not 0 <= cutover_hour <= 23:
        raise ValueError("cutover_hour must be 0..23")
    local = at.astimezone(ZoneInfo(timezone))
    return (local - timedelta(hours=cutover_hour)).date()
