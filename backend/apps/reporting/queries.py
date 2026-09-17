"""
The owner's four questions, in the order they are asked (01-product-spec.md §8).

Everything here reads projections and indexed columns on order_events. Nothing folds the event log
at request time, and nothing scans payload JSON across the whole stream: every payload read below
happens on a set already narrowed by `event_type` and `created_at`, both indexed.

The gross figure is "money taken" — cash through the till, not revenue and not profit.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any

from django.db.models import Avg, Count, F, Q, Sum

from apps.accounts.models import Restaurant, Staff
from apps.floor.models import TableSession
from apps.orders.events import FLAGGED, EventType, is_flagged
from apps.orders.models import Order, OrderEvent, OrderItem, OrderStatus
from apps.payments.models import DrawerMovement, Payment, Shift
from apps.reporting.windows import (
    business_dates,
    current_business_date,
    day_bounds,
    restaurant_zone,
    window_bounds,
)

LIVE_PAYMENTS = Q(voided_at__isnull=True)
VOID_TRIGGER_PAYMENT = "PAYMENT_VOID"
VOID_TRIGGER_MANAGER = "MANAGER"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _staff_names(ids: Iterable[uuid.UUID | None] = ()) -> dict[uuid.UUID, str]:
    wanted = {i for i in ids if i is not None}
    rows = Staff.objects.filter(id__in=wanted) if wanted else Staff.objects.none()
    return {s.id: s.full_name for s in rows}


def _name(names: dict[uuid.UUID, str], staff_id: uuid.UUID | None) -> str | None:
    return names.get(staff_id) if staff_id else None


# ---------------------------------------------------------------- 1. where money can leak


def order_number_gaps(day: date) -> list[int]:
    """Ticket numbers run 1..n per business date. A missing number means a ticket nobody can explain."""
    present: set[int] = {
        n
        for n in Order.objects.filter(business_date=day)
        .exclude(order_number__isnull=True)
        .values_list("order_number", flat=True)
        if n is not None
    }
    if not present:
        return []
    return [n for n in range(1, max(present) + 1) if n not in present]


def _voids_after_acknowledgement(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """
    A void before the kitchen started is routine housekeeping. After it, food was cooked and thrown
    away, so it is a variance and it carries both the actor's and the authoriser's name.
    """
    events = [
        event
        for event in OrderEvent.objects.filter(
            event_type=EventType.ORDER_VOIDED, created_at__gte=start, created_at__lt=end
        ).order_by("-created_at")
        if is_flagged(event.event_type, event.payload)
    ]
    names = _staff_names([e.actor_id for e in events] + [e.authorised_by_id for e in events])
    orders = {
        o.id: o
        for o in Order.objects.filter(id__in=[e.order_id for e in events if e.order_id])
        .select_related("session__table")
        .only("id", "order_number", "session__table__number")
    }
    rows: list[dict[str, Any]] = []
    for event in events:
        order = orders.get(event.order_id) if event.order_id else None
        rows.append(
            {
                "order_id": str(event.order_id) if event.order_id else None,
                "order_number": order.order_number if order else event.payload.get("order_number"),
                "table_number": order.session.table.number if order else None,
                # The total as it stood when the void was authorised, not as it reads today.
                "value_pesewas": int(event.payload.get("total_pesewas") or 0),
                "status_at_void": event.payload.get("status_at_void"),
                "reason_code": event.reason_code,
                "actor": _name(names, event.actor_id),
                "actor_role": event.actor_role,
                "authorised_by": _name(names, event.authorised_by_id),
                "at": _iso(event.created_at),
            }
        )
    return rows


def _discounts_by_staff(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """Who is giving money away, and how much of it. Grouped by the staff member, not the manager."""
    events = list(
        OrderEvent.objects.filter(
            event_type__in=[EventType.DISCOUNT_APPLIED, EventType.COMP_APPLIED],
            created_at__gte=start,
            created_at__lt=end,
        )
    )
    names = _staff_names(e.actor_id for e in events)
    by_staff: dict[str, dict[str, Any]] = {}
    for event in events:
        actor = _name(names, event.actor_id) or "Unknown"
        row = by_staff.setdefault(
            actor,
            {
                "staff": actor,
                "staff_id": str(event.actor_id) if event.actor_id else None,
                "discount_count": 0,
                "discount_pesewas": 0,
                "comp_count": 0,
                "comp_pesewas": 0,
                "value_pesewas": 0,
            },
        )
        amount = int(event.payload.get("amount_pesewas") or 0)
        if event.event_type == EventType.COMP_APPLIED:
            row["comp_count"] += 1
            row["comp_pesewas"] += amount
        else:
            row["discount_count"] += 1
            row["discount_pesewas"] += amount
        row["value_pesewas"] += amount
    return sorted(by_staff.values(), key=lambda r: (-r["value_pesewas"], r["staff"]))


def _reopened_bills(start: datetime, end: datetime) -> list[dict[str, Any]]:
    """
    Reopening a settled bill is the classic leak. Two things reopen one: a manager doing it on purpose,
    and a payment void that takes a settled bill back below its total. They are told apart by whether
    the same command also voided a payment — one command, one idempotency key.
    """
    events = list(
        OrderEvent.objects.filter(
            event_type=EventType.SESSION_REOPENED, created_at__gte=start, created_at__lt=end
        ).order_by("-created_at")
    )
    if not events:
        return []
    void_keys = set(
        OrderEvent.objects.filter(
            event_type=EventType.PAYMENT_VOIDED,
            idempotency_key__in=[e.idempotency_key for e in events],
        ).values_list("idempotency_key", flat=True)
    )
    names = _staff_names([e.actor_id for e in events] + [e.authorised_by_id for e in events])
    return [
        {
            "session_id": str(event.aggregate_id),
            "table_number": event.payload.get("table_number"),
            "trigger": (
                VOID_TRIGGER_PAYMENT if event.idempotency_key in void_keys else VOID_TRIGGER_MANAGER
            ),
            "orders_reopened": len(event.payload.get("order_ids") or []),
            "reason_code": event.reason_code,
            "actor": _name(names, event.actor_id),
            "authorised_by": _name(names, event.authorised_by_id),
            "at": _iso(event.created_at),
        }
        for event in events
    ]


def _cash_variance_by_shift(start: datetime, end: datetime) -> list[dict[str, Any]]:
    shifts = list(
        Shift.objects.filter(closed_at__isnull=False, closed_at__gte=start, closed_at__lt=end)
        .select_related("cashier")
        .order_by("-closed_at")
    )
    return [
        {
            "shift_id": str(shift.id),
            "cashier": shift.cashier.full_name,
            "cashier_id": str(shift.cashier_id),
            "opened_at": _iso(shift.opened_at),
            "closed_at": _iso(shift.closed_at),
            "expected_cash_pesewas": shift.expected_cash_pesewas,
            "declared_cash_pesewas": shift.declared_cash_pesewas,
            "variance_pesewas": shift.variance_pesewas,
        }
        for shift in shifts
    ]


def variance(restaurant: Restaurant, start_day: date, end_day: date) -> dict[str, Any]:
    """Everywhere money can leave without a sale behind it, for one window of business dates."""
    start, end = window_bounds(restaurant, start_day, end_day)
    voids = _voids_after_acknowledgement(start, end)
    shifts = _cash_variance_by_shift(start, end)
    reopened = _reopened_bills(start, end)
    discounts = _discounts_by_staff(start, end)
    gaps = [
        {"business_date": str(day), "missing": missing}
        for day in business_dates(start_day, end_day)
        if (missing := order_number_gaps(day))
    ]

    return {
        "from": str(start_day),
        "to": str(end_day),
        "voids_after_acknowledgement": voids,
        "void_value_pesewas": sum(v["value_pesewas"] for v in voids),
        "discounts_by_staff": discounts,
        "discount_pesewas": sum(r["discount_pesewas"] for r in discounts),
        "comp_pesewas": sum(r["comp_pesewas"] for r in discounts),
        "reopened_bills": reopened,
        "reopened_count": len(reopened),
        "manager_reopens": sum(1 for r in reopened if r["trigger"] == VOID_TRIGGER_MANAGER),
        "cash_variance_by_shift": shifts,
        "cash_variance_pesewas": sum(
            s["variance_pesewas"] for s in shifts if s["variance_pesewas"] is not None
        ),
        "order_number_gaps": gaps,
    }


# ---------------------------------------------------------------- 2. today


def today(restaurant: Restaurant) -> dict[str, Any]:
    """Live from the projections: today has not been rolled up yet, and will not be until cutover."""
    day = current_business_date(restaurant)
    start, end = day_bounds(restaurant, day)

    money_taken = int(
        Payment.objects.filter(
            LIVE_PAYMENTS, recorded_at__gte=start, recorded_at__lt=end
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
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
        # Integer pesewas, floor division. Never a float: a float in a money path does not reconcile
        # against a cash drawer, and round() would bank the exact halves the wrong way besides.
        "average_bill_pesewas": money_taken // bills if bills else 0,
        "open_bills": open_sessions.count(),
        "open_balance_pesewas": open_total - open_paid,
        "orders_closed": Order.objects.filter(business_date=day, status=OrderStatus.CLOSED).count(),
    }


# ---------------------------------------------------------------- 3. patterns


def _money_taken_by_hour(
    restaurant: Restaurant, start: datetime, end: datetime
) -> list[dict[str, int]]:
    """Local hour of the restaurant's own clock, so the peak is where the owner expects it."""
    tz = restaurant_zone(restaurant)
    by_hour: dict[int, int] = {}
    for recorded_at, amount in Payment.objects.filter(
        LIVE_PAYMENTS, recorded_at__gte=start, recorded_at__lt=end
    ).values_list("recorded_at", "amount_pesewas"):
        hour = recorded_at.astimezone(tz).hour
        by_hour[hour] = by_hour.get(hour, 0) + int(amount)
    return [{"hour": hour, "money_taken_pesewas": by_hour[hour]} for hour in sorted(by_hour)]


def _best_sellers(start_day: date, end_day: date, limit: int = 20) -> list[dict[str, Any]]:
    """From the line snapshots, never from menu_items: yesterday's bill keeps yesterday's price."""
    rows = (
        OrderItem.objects.filter(
            order__business_date__gte=start_day, order__business_date__lte=end_day
        )
        .exclude(order__status=OrderStatus.VOIDED)
        .exclude(status="VOIDED")
        .values("name_snapshot")
        .annotate(quantity=Sum("quantity"), value=Sum("line_total_pesewas"))
        .order_by("-value", "name_snapshot")[:limit]
    )
    return [
        {
            "name": row["name_snapshot"],
            "quantity": int(row["quantity"] or 0),
            "value_pesewas": int(row["value"] or 0),
        }
        for row in rows
    ]


def _station_timing(start_day: date, end_day: date) -> list[dict[str, Any]]:
    """Acknowledged → ready, per station. Drinks that never reach the kitchen are not counted."""
    rows = (
        OrderItem.objects.filter(
            order__business_date__gte=start_day,
            order__business_date__lte=end_day,
            order__acknowledged_at__isnull=False,
            order__ready_at__isnull=False,
        )
        .exclude(order__status=OrderStatus.VOIDED)
        .exclude(status="VOIDED")
        .values("prep_station")
        .annotate(
            average=Avg(F("order__ready_at") - F("order__acknowledged_at")), lines=Count("id")
        )
        .order_by("prep_station")
    )
    return [
        {
            "station": row["prep_station"],
            "average_seconds": int(row["average"].total_seconds()) if row["average"] else 0,
            "lines": int(row["lines"]),
        }
        for row in rows
    ]


def patterns(restaurant: Restaurant, start_day: date, end_day: date) -> dict[str, Any]:
    start, end = window_bounds(restaurant, start_day, end_day)
    payments = Payment.objects.filter(LIVE_PAYMENTS, recorded_at__gte=start, recorded_at__lt=end)
    method_mix = {
        row["method"]: int(row["total"] or 0)
        for row in payments.values("method")
        .annotate(total=Sum("amount_pesewas"))
        .order_by("method")
    }
    return {
        "from": str(start_day),
        "to": str(end_day),
        "money_taken_pesewas": sum(method_mix.values()),
        "money_taken_by_hour": _money_taken_by_hour(restaurant, start, end),
        "payment_method_mix": method_mix,
        "best_sellers_by_value": _best_sellers(start_day, end_day),
        "station_timing": _station_timing(start_day, end_day),
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
    """Newest first, paged by seq. Every filter is an indexed column."""
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
        # ORDER_VOIDED is in the set but only counts after acknowledgement, so the payload decides
        # below. Narrowing by type first keeps that read off the rest of the stream.
        rows = rows.filter(event_type__in=sorted(str(t) for t in FLAGGED))

    page = list(rows.order_by("-seq")[: limit + 1])
    has_more = len(page) > limit
    page = page[:limit]
    if flagged_only:
        page = [e for e in page if is_flagged(e.event_type, e.payload)]
    names = _staff_names([e.actor_id for e in page] + [e.authorised_by_id for e in page])

    return {
        "events": [
            {
                "seq": event.seq,
                "type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "aggregate_id": str(event.aggregate_id),
                "order_id": str(event.order_id) if event.order_id else None,
                "actor_id": str(event.actor_id) if event.actor_id else None,
                "actor": _name(names, event.actor_id),
                "actor_role": event.actor_role,
                "authorised_by": _name(names, event.authorised_by_id),
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
    cash_variance = int(
        Shift.objects.filter(closed_at__gte=start, closed_at__lt=end).aggregate(
            s=Sum("variance_pesewas")
        )["s"]
        or 0
    )
    voids_after_ack = _voids_after_acknowledgement(start, end)

    return {
        "money_taken_pesewas": money_taken,
        "covers": int(settled.aggregate(s=Sum("party_size"))["s"] or 0),
        "orders_closed": orders.filter(status=OrderStatus.CLOSED).count(),
        "orders_voided": voided.count(),
        # Only the voids that cost the kitchen something. A round pulled before the kitchen saw it
        # cost nothing and would make this figure lie.
        "void_value_pesewas": sum(v["value_pesewas"] for v in voids_after_ack),
        "discount_pesewas": int(
            orders.exclude(status=OrderStatus.VOIDED).aggregate(s=Sum("discount_pesewas"))["s"] or 0
        ),
        "cash_variance_pesewas": cash_variance,
    }


def drawer_movement_total(restaurant: Restaurant, day: date, kind: str) -> int:
    start, end = day_bounds(restaurant, day)
    return int(
        DrawerMovement.objects.filter(
            kind=kind, recorded_at__gte=start, recorded_at__lt=end
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
