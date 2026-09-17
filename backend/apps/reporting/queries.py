"""
The owner's four questions, in the order they are asked (01-product-spec.md §8).

Everything here reads projections and indexed columns on order_events. Nothing folds the event log
at request time, and nothing scans payload JSON across the whole stream.

The gross figure is "money taken" — cash through the till, not revenue and not profit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import TruncHour
from django.utils import timezone as dj_timezone

from apps.accounts.models import Restaurant, Staff
from apps.core.business_date import business_date
from apps.floor.models import TableSession
from apps.orders.events import FLAGGED, EventType, is_flagged
from apps.orders.models import Order, OrderEvent, OrderItem, OrderStatus
from apps.payments.models import DrawerMovement, Payment, Shift

LIVE_PAYMENTS = Q(voided_at__isnull=True)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _staff_names() -> dict[uuid.UUID, str]:
    return {s.id: s.full_name for s in Staff.objects.all()}


def current_business_date(restaurant: Restaurant, at: datetime | None = None) -> date:
    return business_date(at or dj_timezone.now(), restaurant.timezone, restaurant.day_cutover_hour)


def day_bounds(restaurant: Restaurant, day: date) -> tuple[datetime, datetime]:
    """The window whose events belong to `day`: cutover hour to cutover hour, in the restaurant's zone."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(restaurant.timezone)
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=tz) + timedelta(
        hours=restaurant.day_cutover_hour
    )
    return start_local, start_local + timedelta(days=1)


# ---------------------------------------------------------------- 1. where money can leak


def order_number_gaps(restaurant: Restaurant, day: date) -> list[int]:
    """Ticket numbers run 1..n per business date. A missing number means a ticket nobody can explain."""
    numbers = sorted(
        n
        for n in Order.objects.filter(business_date=day)
        .exclude(order_number__isnull=True)
        .values_list("order_number", flat=True)
    )
    if not numbers:
        return []
    return [n for n in range(1, numbers[-1] + 1) if n not in set(numbers)]


def variance(restaurant: Restaurant, days: int = 7) -> dict[str, Any]:
    since = dj_timezone.now() - timedelta(days=days)
    names = _staff_names()

    voids_after_ack = []
    for event in (
        OrderEvent.objects.filter(event_type=EventType.ORDER_VOIDED, created_at__gte=since)
        .select_related("order")
        .order_by("-created_at")
    ):
        # A void before the kitchen started is routine; after it, food was cooked and thrown away.
        if not is_flagged(event.event_type, event.payload):
            continue
        voids_after_ack.append(
            {
                "order_id": str(event.order_id) if event.order_id else None,
                "order_number": event.payload.get("order_number"),
                "table_number": event.payload.get("table_number"),
                "value_pesewas": int(event.payload.get("total_pesewas") or 0),
                "status_at_void": event.payload.get("status_at_void"),
                "reason_code": event.reason_code,
                "actor": names.get(event.actor_id) if event.actor_id else None,
                "authorised_by": names.get(event.authorised_by_id)
                if event.authorised_by_id
                else None,
                "at": _iso(event.created_at),
            }
        )

    by_staff: dict[str, dict[str, Any]] = {}
    for event in OrderEvent.objects.filter(
        event_type__in=[EventType.DISCOUNT_APPLIED, EventType.COMP_APPLIED],
        created_at__gte=since,
    ):
        actor = names.get(event.actor_id, "Unknown") if event.actor_id else "Unknown"
        row = by_staff.setdefault(
            actor,
            {"staff": actor, "discount_count": 0, "comp_count": 0, "value_pesewas": 0},
        )
        if event.event_type == EventType.COMP_APPLIED:
            row["comp_count"] += 1
        else:
            row["discount_count"] += 1
        row["value_pesewas"] += int(event.payload.get("amount_pesewas") or 0)

    reopened = [
        {
            "session_id": str(event.aggregate_id),
            "table_number": event.payload.get("table_number"),
            "reason_code": event.reason_code,
            "actor": names.get(event.actor_id) if event.actor_id else None,
            "authorised_by": names.get(event.authorised_by_id)
            if event.authorised_by_id
            else None,
            "at": _iso(event.created_at),
        }
        for event in OrderEvent.objects.filter(
            event_type=EventType.SESSION_REOPENED, created_at__gte=since
        ).order_by("-created_at")
    ]

    shifts = [
        {
            "shift_id": str(shift.id),
            "cashier": names.get(shift.cashier_id, "Unknown"),
            "opened_at": _iso(shift.opened_at),
            "closed_at": _iso(shift.closed_at),
            "expected_cash_pesewas": shift.expected_cash_pesewas,
            "declared_cash_pesewas": shift.declared_cash_pesewas,
            "variance_pesewas": shift.variance_pesewas,
        }
        for shift in Shift.objects.filter(
            closed_at__isnull=False, closed_at__gte=since
        ).order_by("-closed_at")
    ]

    today = current_business_date(restaurant)
    gaps = {
        str(day): order_number_gaps(restaurant, day)
        for day in (today - timedelta(days=offset) for offset in range(days))
    }

    return {
        "since": _iso(since),
        "cash_variance_by_shift": shifts,
        "cash_variance_total_pesewas": sum(
            s["variance_pesewas"] or 0 for s in shifts if s["variance_pesewas"] is not None
        ),
        "voids_after_acknowledgement": voids_after_ack,
        "void_value_pesewas": sum(v["value_pesewas"] for v in voids_after_ack),
        "discounts_by_staff": sorted(
            by_staff.values(), key=lambda r: r["value_pesewas"], reverse=True
        ),
        "reopened_bills": reopened,
        "order_number_gaps": {day: numbers for day, numbers in gaps.items() if numbers},
    }


# ---------------------------------------------------------------- 2. today


def today(restaurant: Restaurant) -> dict[str, Any]:
    day = current_business_date(restaurant)
    start, end = day_bounds(restaurant, day)

    payments = Payment.objects.filter(LIVE_PAYMENTS, recorded_at__gte=start, recorded_at__lt=end)
    money_taken = int(payments.aggregate(s=Sum("amount_pesewas"))["s"] or 0)

    settled = TableSession.objects.filter(settled_at__gte=start, settled_at__lt=end)
    covers = int(settled.aggregate(s=Sum("party_size"))["s"] or 0)
    bills = settled.count()

    open_sessions = TableSession.objects.filter(closed_at__isnull=True, settled_at__isnull=True)
    open_total = int(open_sessions.aggregate(s=Sum("bill_total_pesewas"))["s"] or 0)
    open_paid = int(open_sessions.aggregate(s=Sum("paid_pesewas"))["s"] or 0)

    return {
        "business_date": str(day),
        "money_taken_pesewas": money_taken,
        "covers": covers,
        "bills_settled": bills,
        "average_bill_pesewas": round(money_taken / bills) if bills else 0,
        "open_bills": open_sessions.count(),
        "open_balance_pesewas": open_total - open_paid,
        "orders_closed": Order.objects.filter(
            business_date=day, status=OrderStatus.CLOSED
        ).count(),
    }


# ---------------------------------------------------------------- 3. patterns


def patterns(restaurant: Restaurant, days: int = 7) -> dict[str, Any]:
    end_day = current_business_date(restaurant)
    start, _ = day_bounds(restaurant, end_day - timedelta(days=days - 1))
    _, end = day_bounds(restaurant, end_day)

    payments = Payment.objects.filter(LIVE_PAYMENTS, recorded_at__gte=start, recorded_at__lt=end)

    by_hour_rows = (
        payments.annotate(hour=TruncHour("recorded_at"))
        .values("hour")
        .annotate(total=Sum("amount_pesewas"))
        .order_by("hour")
    )
    from zoneinfo import ZoneInfo

    tz = ZoneInfo(restaurant.timezone)
    by_hour: dict[int, int] = {}
    for row in by_hour_rows:
        local_hour = row["hour"].astimezone(tz).hour
        by_hour[local_hour] = by_hour.get(local_hour, 0) + int(row["total"] or 0)

    method_mix = {
        row["method"]: int(row["total"] or 0)
        for row in payments.values("method").annotate(total=Sum("amount_pesewas"))
    }

    best_sellers = [
        {
            "name": row["name_snapshot"],
            "quantity": int(row["quantity"] or 0),
            "value_pesewas": int(row["value"] or 0),
        }
        for row in (
            OrderItem.objects.filter(
                order__business_date__gte=end_day - timedelta(days=days - 1),
                order__business_date__lte=end_day,
            )
            .exclude(order__status=OrderStatus.VOIDED)
            .exclude(status="VOIDED")
            .values("name_snapshot")
            .annotate(quantity=Sum("quantity"), value=Sum("line_total_pesewas"))
            .order_by("-value")[:20]
        )
    ]

    station_rows = (
        OrderItem.objects.filter(
            order__business_date__gte=end_day - timedelta(days=days - 1),
            order__acknowledged_at__isnull=False,
            order__ready_at__isnull=False,
        )
        .exclude(order__status=OrderStatus.VOIDED)
        .values("prep_station")
        .annotate(avg=Avg(F("order__ready_at") - F("order__acknowledged_at")), tickets=Count("id"))
    )
    station_timing = [
        {
            "station": row["prep_station"],
            "average_seconds": int(row["avg"].total_seconds()) if row["avg"] else 0,
            "lines": row["tickets"],
        }
        for row in station_rows
    ]

    return {
        "from": str(end_day - timedelta(days=days - 1)),
        "to": str(end_day),
        "money_taken_by_hour": [
            {"hour": hour, "money_taken_pesewas": by_hour.get(hour, 0)}
            for hour in sorted(by_hour)
        ],
        "payment_method_mix": method_mix,
        "money_taken_pesewas": sum(method_mix.values()),
        "best_sellers_by_value": best_sellers,
        "station_timing": station_timing,
    }


# ---------------------------------------------------------------- 4. every action, in order


def event_log(
    *,
    cursor: int | None = None,
    limit: int = 100,
    actor_id: uuid.UUID | None = None,
    event_type: str | None = None,
    aggregate_type: str | None = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    flagged_only: bool = False,
) -> dict[str, Any]:
    """Newest first, paged by seq. Filters use indexed columns only."""
    limit = max(1, min(200, limit))
    rows = OrderEvent.objects.all()
    if cursor is not None:
        rows = rows.filter(seq__lt=cursor)
    if actor_id is not None:
        rows = rows.filter(actor_id=actor_id)
    if event_type:
        rows = rows.filter(event_type=event_type)
    if aggregate_type:
        rows = rows.filter(aggregate_type=aggregate_type)
    if from_at is not None:
        rows = rows.filter(created_at__gte=from_at)
    if to_at is not None:
        rows = rows.filter(created_at__lt=to_at)
    if flagged_only:
        rows = rows.filter(event_type__in=sorted(str(t) for t in FLAGGED))

    page = list(rows.order_by("-seq")[: limit + 1])
    has_more = len(page) > limit
    page = page[:limit]
    names = _staff_names()

    return {
        "events": [
            {
                "seq": event.seq,
                "type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "order_id": str(event.order_id) if event.order_id else None,
                "actor": names.get(event.actor_id) if event.actor_id else None,
                "actor_role": event.actor_role,
                "authorised_by": names.get(event.authorised_by_id)
                if event.authorised_by_id
                else None,
                "reason_code": event.reason_code,
                "flagged": is_flagged(event.event_type, event.payload),
                "created_at": _iso(event.created_at),
                "payload": event.payload,
            }
            for event in page
        ],
        "next_cursor": page[-1].seq if has_more and page else None,
        "has_more": has_more,
    }


# ---------------------------------------------------------------- the nightly rollup


def rollup_figures(restaurant: Restaurant, day: date) -> dict[str, Any]:
    """What daily_sales stores for one business date. Pure: same inputs, same numbers."""
    start, end = day_bounds(restaurant, day)

    money_taken = int(
        Payment.objects.filter(
            LIVE_PAYMENTS, recorded_at__gte=start, recorded_at__lt=end
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    settled = TableSession.objects.filter(settled_at__gte=start, settled_at__lt=end)
    orders = Order.objects.filter(business_date=day)
    voided = orders.filter(status=OrderStatus.VOIDED)
    variance_total = int(
        Shift.objects.filter(closed_at__gte=start, closed_at__lt=end).aggregate(
            s=Sum("variance_pesewas")
        )["s"]
        or 0
    )

    return {
        "money_taken_pesewas": money_taken,
        "covers": int(settled.aggregate(s=Sum("party_size"))["s"] or 0),
        "orders_closed": orders.filter(status=OrderStatus.CLOSED).count(),
        "orders_voided": voided.count(),
        "void_value_pesewas": int(voided.aggregate(s=Sum("total_pesewas"))["s"] or 0),
        "discount_pesewas": int(
            orders.exclude(status=OrderStatus.VOIDED).aggregate(s=Sum("discount_pesewas"))["s"] or 0
        ),
        "cash_variance_pesewas": variance_total,
    }


def drawer_movement_total(restaurant: Restaurant, day: date, kind: str) -> int:
    start, end = day_bounds(restaurant, day)
    return int(
        DrawerMovement.objects.filter(
            kind=kind, recorded_at__gte=start, recorded_at__lt=end
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
