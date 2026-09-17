"""
What goes on paper, assembled from the projections (WS12).

Both builders read snapshots off `order_items` and never join to `menu_items` — a receipt reprinted
next week must show the price the guest actually paid, not today's menu price (CLAUDE.md invariant 2).

`ticket_envelope()` returns the same shape as an ORDER_SUBMITTED SSE envelope so that
render.render_kitchen_ticket() has exactly one input format whether the ticket came off the live
stream or was rebuilt here for a reprint.
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.floor.models import TableSession
from apps.orders.models import Order, OrderItemStatus, OrderStatus
from apps.payments.models import Payment, PaymentMethod


def _iso(value: Any) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _line(item: Any) -> dict[str, Any]:
    """The printable line. Snapshot fields only."""
    return {
        "item_id": str(item.id),
        "name": item.name_snapshot,
        "name_snapshot": item.name_snapshot,
        "unit_price_pesewas": int(item.unit_price_pesewas),
        "prep_station": item.prep_station,
        "quantity": int(item.quantity),
        "modifiers": list(item.modifiers or []),
        "notes": item.notes or "",
        "course": int(item.course),
        "line_total_pesewas": int(item.line_total_pesewas),
    }


def ticket_envelope(order: Order) -> dict[str, Any]:
    """Rebuild the ORDER_SUBMITTED envelope for `order` from the projection."""
    items = order.items.exclude(status=OrderItemStatus.VOIDED).order_by("sort_order", "id")
    lines = [_line(item) for item in items]
    return {
        "id": str(order.id),
        "type": "ORDER_SUBMITTED",
        "aggregate_type": "ORDER",
        "aggregate_id": str(order.id),
        "order_id": str(order.id),
        # Server time, not the device's claim (CLAUDE.md invariant 6).
        "created_at": _iso(order.submitted_at or order.created_at),
        "payload": {
            "order_number": order.order_number,
            "business_date": order.business_date.isoformat() if order.business_date else None,
            "session_id": str(order.session_id),
            "table_number": order.session.table.number,
            "origin": order.origin,
            "lines": lines,
            "subtotal_pesewas": int(order.subtotal_pesewas),
            "discount_pesewas": int(order.discount_pesewas),
            "total_pesewas": int(order.total_pesewas),
        },
    }


def stations_on(order: Order) -> list[str]:
    """Which prep stations have work on this order — one ticket per station printer."""
    seen: list[str] = []
    for item in order.items.exclude(status=OrderItemStatus.VOIDED):
        if item.prep_station not in seen:
            seen.append(item.prep_station)
    return sorted(seen)


def receipt_payload(session: TableSession, *, reprint: bool = False) -> dict[str, Any]:
    """
    The guest's sales record for one bill.

    No tax line, no VAT/levy split, no GRA fiscal reference — there is nothing to compute and
    nothing to print (ADR-0005). `total_pesewas` is the sum of menu prices less discounts, which is
    exactly what the guest was asked for.
    """
    orders = (
        Order.objects.filter(session_id=session.id)
        .exclude(status=OrderStatus.VOIDED)
        .prefetch_related("items")
        .order_by("created_at")
    )

    lines: list[dict[str, Any]] = []
    discounts: list[dict[str, Any]] = []
    subtotal = 0
    total = 0
    for order in orders:
        for item in order.items.exclude(status=OrderItemStatus.VOIDED).order_by("sort_order", "id"):
            line = _line(item)
            line["order_number"] = order.order_number
            lines.append(line)
        subtotal += int(order.subtotal_pesewas)
        total += int(order.total_pesewas)
        if int(order.discount_pesewas) > 0:
            discounts.append(
                {
                    "order_number": order.order_number,
                    "label": f"Discount (#{order.order_number})",
                    "discount_pesewas": int(order.discount_pesewas),
                }
            )

    live_payments = list(
        Payment.objects.filter(session_id=session.id, voided_at__isnull=True).order_by(
            "recorded_at"
        )
    )
    payments = [
        {
            "method": payment.method,
            "amount_pesewas": int(payment.amount_pesewas),
            "external_reference": payment.external_reference,
            "recorded_at": _iso(payment.recorded_at),
        }
        for payment in live_payments
    ]
    # Change is only ever real for cash; a MoMo or card tender has none.
    change = sum(
        int(p.change_pesewas or 0) for p in live_payments if p.method == PaymentMethod.CASH
    )
    paid = sum(int(p.amount_pesewas) for p in live_payments)

    return {
        "restaurant_name": session.restaurant.name,
        "address_lines": ["Shiashi, Accra"],
        "session_id": str(session.id),
        "table_number": session.table.number,
        "served_by": session.opened_by.full_name if session.opened_by_id else "",
        "opened_at": _iso(session.opened_at),
        "settled_at": _iso(session.settled_at),
        "printed_at": _iso(timezone.now()),
        "reprint": reprint,
        "lines": lines,
        "discounts": discounts,
        "subtotal_pesewas": subtotal,
        "total_pesewas": total,
        "payments": payments,
        "paid_pesewas": paid,
        "change_pesewas": change,
        "balance_pesewas": total - paid,
    }
