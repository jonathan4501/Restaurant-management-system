"""
Reporting background work: the nightly rollup and the summary that follows it.

Beat cannot know each restaurant's cutover hour, so `rollup_due_restaurants` runs every hour and does
nothing except for the restaurants whose service has just ended. That keeps a per-restaurant cutover
working without a schedule entry per tenant, and it makes a missed hour harmless: the rollup is an
idempotent upsert, so re-running it changes nothing.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta

from celery import shared_task
from django.utils.dateparse import parse_date

from apps.accounts.models import Restaurant
from apps.core.tenancy import restaurant_context
from apps.reporting.rollup import previous_business_date, rollup_daily_sales
from apps.reporting.summary import send_summary
from apps.reporting.windows import current_business_date, restaurant_zone

log = logging.getLogger(__name__)

ROLLUP_MINUTE = 10  # cutover hour + 10 minutes, per docs/tasks/WS06-reporting.md §1


def _restaurant(restaurant_id: str | uuid.UUID) -> Restaurant:
    return Restaurant.objects.get(pk=uuid.UUID(str(restaurant_id)))


def _as_date(value: str | date | None, restaurant: Restaurant) -> date:
    if value is None:
        return previous_business_date(restaurant)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    parsed = parse_date(str(value))
    if parsed is None:
        raise ValueError(f"not a business date: {value!r}")
    return parsed


@shared_task(name="reporting.rollup_daily_sales")
def rollup_daily_sales_task(restaurant_id: str, business_date: str | None = None) -> dict[str, int]:
    """One restaurant, one business date. Defaults to the service that has just ended."""
    restaurant = _restaurant(restaurant_id)
    day = _as_date(business_date, restaurant)
    with restaurant_context(restaurant.id):
        row = rollup_daily_sales(restaurant, day)
        log.info(
            "rolled up %s for %s: money taken %s pesewas",
            day,
            restaurant.name,
            row.money_taken_pesewas,
        )
        return {"money_taken_pesewas": int(row.money_taken_pesewas), "covers": row.covers}


@shared_task(name="reporting.send_daily_summary")
def send_daily_summary(restaurant_id: str, business_date: str | None = None) -> bool:
    """The short text the owner reads at close. Runs after the rollup, off the same figures."""
    from apps.reporting.models import DailySales

    restaurant = _restaurant(restaurant_id)
    day = _as_date(business_date, restaurant)
    with restaurant_context(restaurant.id):
        row = DailySales.objects.filter(business_date=day).first()
        if row is None:
            row = rollup_daily_sales(restaurant, day)
        return send_summary(restaurant, row)


@shared_task(name="reporting.rollup_due_restaurants")
def rollup_due_restaurants() -> list[str]:
    """
    Beat's hourly knock. Rolls up and summarises only the restaurants whose cutover hour has just
    passed in their own timezone.
    """
    due: list[str] = []
    for restaurant in Restaurant.objects.filter(is_active=True):
        local_hour = datetime.now(restaurant_zone(restaurant)).hour
        if local_hour != restaurant.day_cutover_hour:
            continue
        day = previous_business_date(restaurant)
        rollup_daily_sales_task.delay(str(restaurant.id), str(day))
        send_daily_summary.delay(str(restaurant.id), str(day))
        due.append(str(restaurant.id))
    return due


@shared_task(name="reporting.rollup_backfill")
def rollup_backfill(restaurant_id: str, days: int = 7) -> int:
    """Rebuild the last `days` business dates. `daily_sales` is derived, so this is always safe."""
    restaurant = _restaurant(restaurant_id)
    with restaurant_context(restaurant.id):
        today = current_business_date(restaurant)
        for offset in range(1, days + 1):
            rollup_daily_sales(restaurant, today - timedelta(days=offset))
    return days
