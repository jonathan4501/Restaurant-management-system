"""Shared helpers for order command handlers."""

from __future__ import annotations

import uuid
from typing import Any

from apps.core.errors import ApiError, ErrorCode
from apps.core.uuid7 import is_uuid7
from apps.floor.models import TableSession
from apps.orders.events import LineSnapshot
from apps.orders.models import Order, OrderItem, OrderItemStatus
from apps.orders.state_machine import OrderCommand, Transition, transition
from apps.orders.totals import order_total


def require_uuid7(value: uuid.UUID | str, field: str = "id") -> uuid.UUID:
    if not is_uuid7(value):
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a client-generated UUIDv7.",
            errors={field: ["Must be UUIDv7."]},
        )
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def lock_order(order_id: uuid.UUID) -> Order:
    try:
        return (
            Order.objects.select_for_update()
            .select_related("session", "session__table")
            .get(pk=order_id)
        )
    except Order.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order not found.") from err


def lock_open_session(session_id: uuid.UUID) -> TableSession:
    try:
        session = (
            TableSession.objects.select_for_update().select_related("table").get(pk=session_id)
        )
    except TableSession.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err
    if session.closed_at is not None:
        raise ApiError(409, ErrorCode.SESSION_CLOSED, "Session is closed.")
    return session


def assert_transition(order: Order, command: OrderCommand) -> Transition:
    return transition(order.status, command)


def active_items(order: Order) -> list[OrderItem]:
    return list(order.items.exclude(status=OrderItemStatus.VOIDED).order_by("sort_order", "id"))


def compute_totals(line_totals: list[int], discount_pesewas: int) -> tuple[int, int]:
    subtotal = sum(line_totals)
    return subtotal, order_total(line_totals, discount_pesewas)


def as_line_dict(
    *,
    item_id: uuid.UUID,
    menu_item_id: uuid.UUID,
    name: str,
    unit_price_pesewas: int,
    prep_station: str,
    quantity: int,
    modifiers: list[dict[str, Any]],
    notes: str,
    course: int,
    line_total_pesewas: int,
) -> dict[str, Any]:
    snap = LineSnapshot(
        item_id=str(item_id),
        menu_item_id=str(menu_item_id),
        name=name,
        unit_price_pesewas=unit_price_pesewas,
        prep_station=prep_station,
        quantity=quantity,
        modifiers=modifiers,
        notes=notes,
        course=course,
        line_total_pesewas=line_total_pesewas,
    )
    return {
        "item_id": snap.item_id,
        "menu_item_id": snap.menu_item_id,
        "name": snap.name,
        "unit_price_pesewas": snap.unit_price_pesewas,
        "prep_station": snap.prep_station,
        "quantity": snap.quantity,
        "modifiers": list(snap.modifiers),
        "notes": snap.notes,
        "course": snap.course,
        "line_total_pesewas": snap.line_total_pesewas,
    }


def item_to_line_dict(item: OrderItem) -> dict[str, Any]:
    return as_line_dict(
        item_id=item.id,
        menu_item_id=item.menu_item_id,
        name=item.name_snapshot,
        unit_price_pesewas=int(item.unit_price_pesewas),
        prep_station=item.prep_station,
        quantity=int(item.quantity),
        modifiers=list(item.modifiers or []),
        notes=item.notes or "",
        course=int(item.course),
        line_total_pesewas=int(item.line_total_pesewas),
    )


def order_response(order: Order) -> dict[str, Any]:
    items = [item_to_line_dict(i) for i in active_items(order)]
    return {
        "id": str(order.id),
        "session_id": str(order.session_id),
        "status": order.status,
        "order_number": order.order_number,
        "business_date": order.business_date.isoformat() if order.business_date else None,
        "origin": order.origin,
        "subtotal_pesewas": int(order.subtotal_pesewas),
        "discount_pesewas": int(order.discount_pesewas),
        "total_pesewas": int(order.total_pesewas),
        "items": items,
        "submitted_at": (
            order.submitted_at.isoformat().replace("+00:00", "Z") if order.submitted_at else None
        ),
        "acknowledged_at": (
            order.acknowledged_at.isoformat().replace("+00:00", "Z")
            if order.acknowledged_at
            else None
        ),
        "ready_at": (order.ready_at.isoformat().replace("+00:00", "Z") if order.ready_at else None),
        "served_at": (
            order.served_at.isoformat().replace("+00:00", "Z") if order.served_at else None
        ),
        "voided_at": (
            order.voided_at.isoformat().replace("+00:00", "Z") if order.voided_at else None
        ),
    }
