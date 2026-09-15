"""
Whether a wall-clock moment falls inside Restaurant.service_start / service_end.

WS02 owns the gating helper; the TimeFields live on accounts.Restaurant (already present
from WS00). If either field is missing, we treat the moment as "during service" so
PRICE_CHANGE_IN_SERVICE authorisation is required — fail closed.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.accounts.models import Restaurant


def is_during_service(restaurant: Restaurant, at: datetime | None = None) -> bool:
    """True when `at` (default: now, restaurant-local) is inside service hours."""
    start = getattr(restaurant, "service_start", None)
    end = getattr(restaurant, "service_end", None)
    if not isinstance(start, time) or not isinstance(end, time):
        return True  # fail closed — require authorisation

    if at is None:
        at = timezone.now()
    if at.tzinfo is None:
        raise ValueError("is_during_service needs an aware datetime")

    local = at.astimezone(ZoneInfo(restaurant.timezone))
    clock = local.timetz().replace(tzinfo=None)

    if start <= end:
        return start <= clock < end
    # Overnight window (e.g. 18:00 → 02:00).
    return clock >= start or clock < end
