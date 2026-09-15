"""Read helpers: order detail, session bill."""

from __future__ import annotations

from typing import Any

from apps.floor.models import TableSession
from apps.floor.state_chip import session_state_chip
from apps.orders.commands._common import item_to_line_dict, order_response
from apps.orders.models import Order, OrderStatus


def serialize_order(order: Order) -> dict[str, Any]:
    return order_response(order)


def serialize_bill(session: TableSession) -> dict[str, Any]:
    orders = (
        Order.objects.filter(session_id=session.id)
        .exclude(status=OrderStatus.VOIDED)
        .prefetch_related("items")
        .order_by("created_at")
    )
    lines: list[dict[str, Any]] = []
    discounts: list[dict[str, Any]] = []
    for order in orders:
        for item in order.items.exclude(status="VOIDED"):
            line = item_to_line_dict(item)
            line["order_id"] = str(order.id)
            line["order_number"] = order.order_number
            lines.append(line)
        if int(order.discount_pesewas) > 0:
            discounts.append(
                {
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "discount_pesewas": int(order.discount_pesewas),
                }
            )
    return {
        "session_id": str(session.id),
        "table_id": str(session.table_id),
        "table_number": session.table.number,
        "lines": lines,
        "discounts": discounts,
        "bill_total_pesewas": int(session.bill_total_pesewas),
        "paid_pesewas": int(session.paid_pesewas),
        "balance_pesewas": session.balance_pesewas,
        "orders": [serialize_order(o) for o in orders],
    }


def serialize_session(session: TableSession) -> dict[str, Any]:
    orders = list(Order.objects.filter(session_id=session.id).order_by("created_at"))
    statuses = [o.status for o in orders]
    return {
        "id": str(session.id),
        "table_id": str(session.table_id),
        "table_number": session.table.number,
        "party_size": session.party_size,
        "opened_at": session.opened_at.isoformat().replace("+00:00", "Z"),
        "closed_at": (
            session.closed_at.isoformat().replace("+00:00", "Z") if session.closed_at else None
        ),
        "bill_total_pesewas": int(session.bill_total_pesewas),
        "paid_pesewas": int(session.paid_pesewas),
        "balance_pesewas": session.balance_pesewas,
        "settled_at": (
            session.settled_at.isoformat().replace("+00:00", "Z") if session.settled_at else None
        ),
        "state": session_state_chip(
            statuses=statuses,
            paid_pesewas=int(session.paid_pesewas),
            bill_total_pesewas=int(session.bill_total_pesewas),
        ),
        "order_count": len(orders),
        "orders": [serialize_order(o) for o in orders],
        "payments": [],  # WS05
    }


def serialize_table(table, open_session: TableSession | None) -> dict[str, Any]:
    summary = None
    if open_session is not None:
        orders = list(Order.objects.filter(session_id=open_session.id))
        summary = {
            "id": str(open_session.id),
            "opened_at": open_session.opened_at.isoformat().replace("+00:00", "Z"),
            "bill_total_pesewas": int(open_session.bill_total_pesewas),
            "paid_pesewas": int(open_session.paid_pesewas),
            "balance_pesewas": open_session.balance_pesewas,
            "order_count": len(orders),
            "state": session_state_chip(
                statuses=[o.status for o in orders],
                paid_pesewas=int(open_session.paid_pesewas),
                bill_total_pesewas=int(open_session.bill_total_pesewas),
            ),
        }
    return {
        "id": str(table.id),
        "number": table.number,
        "seats": table.seats,
        "is_active": table.is_active,
        "open_session": summary,
    }


def kds_tickets(*, station: str | None = None) -> list[dict[str, Any]]:
    qs = (
        Order.objects.filter(status__in=["SUBMITTED", "PREPARING", "READY"])
        .select_related("session", "session__table")
        .prefetch_related("items")
        .order_by("submitted_at", "created_at")
    )
    out: list[dict[str, Any]] = []
    for order in qs:
        items = list(order.items.exclude(status="VOIDED"))
        if station:
            items = [i for i in items if i.prep_station == station]
            if not items:
                continue
        out.append(
            {
                "order_id": str(order.id),
                "order_number": order.order_number,
                "table_number": order.session.table.number,
                "status": order.status,
                "submitted_at": (
                    order.submitted_at.isoformat().replace("+00:00", "Z")
                    if order.submitted_at
                    else None
                ),
                "acknowledged_at": (
                    order.acknowledged_at.isoformat().replace("+00:00", "Z")
                    if order.acknowledged_at
                    else None
                ),
                "ready_at": (
                    order.ready_at.isoformat().replace("+00:00", "Z") if order.ready_at else None
                ),
                "items": [item_to_line_dict(i) for i in items],
            }
        )
    return out
