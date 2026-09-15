"""Projections for ORDER events. Deterministic; use event.created_at; never read menu_items."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from django.db.models import Sum

from apps.core.projections import project
from apps.floor.models import TableSession
from apps.orders.events import EventType
from apps.orders.models import Order, OrderEvent, OrderItem, OrderItemStatus, OrderStatus


def _refresh_session_bill(restaurant_id: uuid.UUID, session_id: uuid.UUID) -> None:
    total = (
        Order.objects.unscoped()
        .filter(restaurant_id=restaurant_id, session_id=session_id)
        .exclude(status=OrderStatus.VOIDED)
        .aggregate(s=Sum("total_pesewas"))["s"]
        or 0
    )
    TableSession.objects.unscoped().filter(restaurant_id=restaurant_id, id=session_id).update(
        bill_total_pesewas=int(total)
    )


def _line_fields(line: dict[str, Any]) -> dict[str, Any]:
    return {
        "menu_item_id": uuid.UUID(line["menu_item_id"]),
        "name_snapshot": line["name"],
        "unit_price_pesewas": int(line["unit_price_pesewas"]),
        "prep_station": line["prep_station"],
        "quantity": int(line["quantity"]),
        "modifiers": line.get("modifiers") or [],
        "notes": line.get("notes") or "",
        "course": int(line.get("course") or 1),
        "line_total_pesewas": int(line["line_total_pesewas"]),
    }


@project(EventType.ORDER_OPENED)
def order_opened(event: OrderEvent) -> None:
    payload = event.payload
    Order.objects.update_or_create(
        id=event.aggregate_id,
        defaults={
            "restaurant_id": event.restaurant_id,
            "session_id": uuid.UUID(payload["session_id"]),
            "status": OrderStatus.DRAFT,
            "subtotal_pesewas": 0,
            "discount_pesewas": 0,
            "total_pesewas": 0,
            "placed_by_id": event.actor_id,
            "origin": payload.get("origin") or "WAITER",
            "created_at": event.created_at,
        },
    )


@project(EventType.ITEM_ADDED)
def item_added(event: OrderEvent) -> None:
    line = event.payload["line"]
    item_id = uuid.UUID(line["item_id"])
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    sort_order = order.items.count()
    OrderItem.objects.update_or_create(
        id=item_id,
        defaults={
            "restaurant_id": event.restaurant_id,
            "order_id": order.id,
            **_line_fields(line),
            "status": OrderItemStatus.PENDING,
            "sort_order": sort_order,
        },
    )
    order.subtotal_pesewas = int(event.payload["subtotal_pesewas"])
    order.total_pesewas = int(event.payload["total_pesewas"])
    order.save(update_fields=["subtotal_pesewas", "total_pesewas"])
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.ITEM_REMOVED)
def item_removed(event: OrderEvent) -> None:
    item_id = uuid.UUID(event.payload["item_id"])
    OrderItem.objects.unscoped().filter(restaurant_id=event.restaurant_id, id=item_id).delete()
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.subtotal_pesewas = int(event.payload["subtotal_pesewas"])
    order.total_pesewas = int(event.payload["total_pesewas"])
    order.save(update_fields=["subtotal_pesewas", "total_pesewas"])
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.ITEM_MODIFIED)
def item_modified(event: OrderEvent) -> None:
    line = event.payload["line"]
    item_id = uuid.UUID(line["item_id"])
    OrderItem.objects.unscoped().filter(restaurant_id=event.restaurant_id, id=item_id).update(
        **_line_fields(line)
    )
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.subtotal_pesewas = int(event.payload["subtotal_pesewas"])
    order.total_pesewas = int(event.payload["total_pesewas"])
    order.save(update_fields=["subtotal_pesewas", "total_pesewas"])
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.ORDER_SUBMITTED)
def order_submitted(event: OrderEvent) -> None:
    payload = event.payload
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.status = OrderStatus.SUBMITTED
    order.order_number = int(payload["order_number"])
    order.business_date = date.fromisoformat(payload["business_date"])
    order.subtotal_pesewas = int(payload["subtotal_pesewas"])
    order.discount_pesewas = int(payload["discount_pesewas"])
    order.total_pesewas = int(payload["total_pesewas"])
    order.submitted_at = event.created_at
    order.save(
        update_fields=[
            "status",
            "order_number",
            "business_date",
            "subtotal_pesewas",
            "discount_pesewas",
            "total_pesewas",
            "submitted_at",
        ]
    )
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.KITCHEN_ACKNOWLEDGED)
def kitchen_acknowledged(event: OrderEvent) -> None:
    Order.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(status=OrderStatus.PREPARING, acknowledged_at=event.created_at)


@project(EventType.ITEM_STARTED)
def item_started(event: OrderEvent) -> None:
    item_id = uuid.UUID(event.payload["item_id"])
    OrderItem.objects.unscoped().filter(restaurant_id=event.restaurant_id, id=item_id).update(
        status=OrderItemStatus.PREPARING
    )
    Order.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id, status=OrderStatus.SUBMITTED
    ).update(status=OrderStatus.PREPARING, acknowledged_at=event.created_at)


@project(EventType.ITEM_READY)
def item_ready(event: OrderEvent) -> None:
    item_id = uuid.UUID(event.payload["item_id"])
    OrderItem.objects.unscoped().filter(restaurant_id=event.restaurant_id, id=item_id).update(
        status=OrderItemStatus.READY
    )


@project(EventType.ORDER_READY)
def order_ready(event: OrderEvent) -> None:
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.status = OrderStatus.READY
    order.ready_at = event.created_at
    if order.acknowledged_at is None:
        order.acknowledged_at = event.created_at
    order.save(update_fields=["status", "ready_at", "acknowledged_at"])
    OrderItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, order_id=order.id
    ).exclude(status=OrderItemStatus.VOIDED).update(status=OrderItemStatus.READY)


@project(EventType.ORDER_SERVED)
def order_served(event: OrderEvent) -> None:
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.status = OrderStatus.SERVED
    order.served_at = event.created_at
    order.save(update_fields=["status", "served_at"])
    OrderItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, order_id=order.id
    ).exclude(status=OrderItemStatus.VOIDED).update(status=OrderItemStatus.SERVED)


@project(EventType.COURSE_FIRED)
def course_fired(event: OrderEvent) -> None:
    del event  # Phase 4 — event may exist in the stream; no projection columns yet.


@project(EventType.DISCOUNT_APPLIED)
def discount_applied(event: OrderEvent) -> None:
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.subtotal_pesewas = int(event.payload["subtotal_pesewas"])
    order.discount_pesewas = int(event.payload["amount_pesewas"])
    order.total_pesewas = int(event.payload["total_pesewas"])
    order.authorised_by_id = event.authorised_by_id
    order.save(
        update_fields=["subtotal_pesewas", "discount_pesewas", "total_pesewas", "authorised_by_id"]
    )
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.COMP_APPLIED)
def comp_applied(event: OrderEvent) -> None:
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.subtotal_pesewas = int(event.payload["subtotal_pesewas"])
    order.discount_pesewas = int(event.payload["amount_pesewas"])
    order.total_pesewas = int(event.payload["total_pesewas"])
    order.authorised_by_id = event.authorised_by_id
    order.save(
        update_fields=["subtotal_pesewas", "discount_pesewas", "total_pesewas", "authorised_by_id"]
    )
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.PRICE_OVERRIDDEN)
def price_overridden(event: OrderEvent) -> None:
    item_id = uuid.UUID(event.payload["item_id"])
    item = OrderItem.objects.unscoped().get(restaurant_id=event.restaurant_id, id=item_id)
    new_unit = int(event.payload["new_unit_price_pesewas"])
    extras = sum(int(m.get("price_pesewas", 0)) for m in (item.modifiers or []))
    item.unit_price_pesewas = new_unit
    item.line_total_pesewas = (new_unit + extras) * int(item.quantity)
    item.save(update_fields=["unit_price_pesewas", "line_total_pesewas"])
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.subtotal_pesewas = int(event.payload["subtotal_pesewas"])
    order.total_pesewas = int(event.payload["total_pesewas"])
    order.authorised_by_id = event.authorised_by_id
    order.save(update_fields=["subtotal_pesewas", "total_pesewas", "authorised_by_id"])
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.ORDER_VOIDED)
def order_voided(event: OrderEvent) -> None:
    order = Order.objects.unscoped().get(restaurant_id=event.restaurant_id, id=event.aggregate_id)
    order.status = OrderStatus.VOIDED
    order.voided_at = event.created_at
    order.void_reason = event.reason_code
    order.voided_by_id = event.actor_id
    order.authorised_by_id = event.authorised_by_id
    order.save(
        update_fields=[
            "status",
            "voided_at",
            "void_reason",
            "voided_by_id",
            "authorised_by_id",
        ]
    )
    OrderItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, order_id=order.id
    ).update(status=OrderItemStatus.VOIDED)
    _refresh_session_bill(event.restaurant_id, order.session_id)


@project(EventType.ORDER_CLOSED)
def order_closed(event: OrderEvent) -> None:
    Order.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(status=OrderStatus.CLOSED, closed_at=event.created_at)


@project(EventType.ORDER_REOPENED)
def order_reopened(event: OrderEvent) -> None:
    Order.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(status=OrderStatus.SERVED, closed_at=None)
