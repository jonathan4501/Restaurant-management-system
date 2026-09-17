"""
The nightly rollup.

`daily_sales` is a materialised read model, not a source of truth: every figure in it is derived from
`order_events` and the projections, so it can be thrown away and rebuilt for any date at any time.
That is why this writes the row directly instead of going through the command runner — there is no
aggregate here to change, only arithmetic to cache. Running it twice for the same date must leave one
row with the same numbers, so it is an upsert keyed by (restaurant, business_date).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.utils import timezone as dj_timezone

from apps.accounts.models import Restaurant
from apps.reporting.models import DailySales
from apps.reporting.queries import rollup_figures
from apps.reporting.windows import current_business_date


def rollup_daily_sales(restaurant: Restaurant, day: date) -> DailySales:
    """
    Idempotent upsert of one business date.

    Two of the columns need their meaning stated, because the obvious reading of each is wrong:

    - `void_value_pesewas` counts only voids **after the kitchen acknowledged** the order. A round
      pulled before anybody cooked it cost the restaurant nothing, and including it would make the
      owner chase a loss that never happened. `orders_voided` counts every void, either kind.
    - `discount_pesewas` is money given away: discounts **and** comps. Both land in
      `orders.discount_pesewas`, and from the owner's side of the till they are the same event —
      food left the kitchen and no money came back for it.
    """
    figures = rollup_figures(restaurant, day)
    row, _ = DailySales.objects.update_or_create(
        restaurant_id=restaurant.id,
        business_date=day,
        defaults={**figures, "computed_at": dj_timezone.now()},
    )
    return row


def previous_business_date(restaurant: Restaurant) -> date:
    """The service that has just ended, which is what a task running after cutover rolls up."""
    return current_business_date(restaurant) - timedelta(days=1)


def serialize_daily_sales(row: DailySales) -> dict[str, Any]:
    return {
        "business_date": str(row.business_date),
        "money_taken_pesewas": int(row.money_taken_pesewas),
        "covers": row.covers,
        "orders_closed": row.orders_closed,
        "orders_voided": row.orders_voided,
        "void_value_pesewas": int(row.void_value_pesewas),
        "discount_pesewas": int(row.discount_pesewas),
        "cash_variance_pesewas": row.cash_variance_pesewas,
        "computed_at": row.computed_at.isoformat().replace("+00:00", "Z"),
    }
