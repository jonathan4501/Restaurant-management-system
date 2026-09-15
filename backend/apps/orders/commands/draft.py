"""Order open + draft line commands."""

from __future__ import annotations

import uuid
from typing import Any

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.roles import AggregateType
from apps.menu.models import MenuItem
from apps.menu.snapshot import snapshot_line
from apps.orders.commands._common import (
    active_items,
    as_line_dict,
    assert_transition,
    compute_totals,
    item_to_line_dict,
    lock_open_session,
    lock_order,
    order_response,
    require_uuid7,
)
from apps.orders.events import EventType, ItemAdded, ItemModified, ItemRemoved, OrderOpened
from apps.orders.models import Order, OrderItem, OrderOrigin
from apps.orders.state_machine import OrderCommand


def open_order(
    ctx: CommandContext, data: dict[str, Any], *, origin: str | None = None
) -> CommandOutcome:
    order_id = require_uuid7(data["id"])
    session_id = data["session_id"]
    session = lock_open_session(session_id)

    if Order.objects.filter(pk=order_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Order id already exists.")

    resolved_origin = origin or (
        OrderOrigin.WAITER if ctx.actor_role.value != "GUEST" else OrderOrigin.GUEST_TABLET
    )

    payload = OrderOpened(
        session_id=str(session.id),
        table_number=session.table.number,
        origin=resolved_origin,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order_id,
                EventType.ORDER_OPENED,
                payload,
                order_id=order_id,
                event_id=order_id,
            )
        ],
        response={
            "id": str(order_id),
            "session_id": str(session.id),
            "status": "DRAFT",
            "origin": resolved_origin,
            "items": [],
            "subtotal_pesewas": 0,
            "discount_pesewas": 0,
            "total_pesewas": 0,
        },
        status=201,
    )


def add_item(ctx: CommandContext, order_id: uuid.UUID, data: dict[str, Any]) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.ADD_ITEM)

    item_id = require_uuid7(data["id"])
    if OrderItem.objects.filter(pk=item_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Item id already exists.")

    try:
        menu_item = MenuItem.objects.get(pk=data["menu_item_id"])
    except MenuItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Menu item not found.") from err

    quantity = int(data["quantity"])
    modifier_ids = list(data.get("modifier_ids") or [])
    notes = data.get("notes") or ""
    course = int(data.get("course") or 1)

    snap = snapshot_line(menu_item, modifier_ids, quantity)
    line = as_line_dict(
        item_id=item_id,
        menu_item_id=menu_item.id,
        name=snap.name,
        unit_price_pesewas=snap.unit_price_pesewas,
        prep_station=snap.prep_station,
        quantity=quantity,
        modifiers=list(snap.modifiers),
        notes=notes,
        course=course,
        line_total_pesewas=snap.line_total_pesewas,
    )

    from apps.orders.events import LineSnapshot as LS

    existing_totals = [int(i.line_total_pesewas) for i in active_items(order)]
    subtotal, total = compute_totals(
        existing_totals + [snap.line_total_pesewas], int(order.discount_pesewas)
    )
    payload = ItemAdded(
        line=LS(**line),
        subtotal_pesewas=subtotal,
        total_pesewas=total,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ITEM_ADDED,
                payload,
                order_id=order.id,
            )
        ],
        response={
            **order_response(order),
            "items": [item_to_line_dict(i) for i in active_items(order)] + [line],
            "subtotal_pesewas": subtotal,
            "total_pesewas": total,
            "added_item": line,
        },
    )


def remove_item(ctx: CommandContext, order_id: uuid.UUID, item_id: uuid.UUID) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.REMOVE_ITEM)

    try:
        item = OrderItem.objects.select_for_update().get(pk=item_id, order_id=order.id)
    except OrderItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order item not found.") from err

    remaining = [int(i.line_total_pesewas) for i in active_items(order) if i.id != item.id]
    subtotal, total = compute_totals(remaining, int(order.discount_pesewas))
    payload = ItemRemoved(
        item_id=str(item.id), subtotal_pesewas=subtotal, total_pesewas=total
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ITEM_REMOVED,
                payload,
                order_id=order.id,
            )
        ],
        response={
            "id": str(order.id),
            "removed_item_id": str(item.id),
            "subtotal_pesewas": subtotal,
            "total_pesewas": total,
        },
    )


def modify_item(
    ctx: CommandContext, order_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.MODIFY_ITEM)

    try:
        item = OrderItem.objects.select_for_update().get(pk=item_id, order_id=order.id)
    except OrderItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order item not found.") from err

    try:
        menu_item = MenuItem.objects.get(pk=item.menu_item_id)
    except MenuItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Menu item not found.") from err

    quantity = int(data.get("quantity", item.quantity))
    modifier_ids = data.get("modifier_ids")
    if modifier_ids is None:
        modifier_ids = [uuid.UUID(m["id"]) for m in (item.modifiers or [])]
    notes = data["notes"] if "notes" in data else (item.notes or "")
    course = int(data.get("course", item.course))

    snap = snapshot_line(menu_item, modifier_ids, quantity)
    line = as_line_dict(
        item_id=item.id,
        menu_item_id=menu_item.id,
        name=snap.name,
        unit_price_pesewas=snap.unit_price_pesewas,
        prep_station=snap.prep_station,
        quantity=quantity,
        modifiers=list(snap.modifiers),
        notes=notes,
        course=course,
        line_total_pesewas=snap.line_total_pesewas,
    )

    from apps.orders.events import LineSnapshot as LS

    remaining = [
        snap.line_total_pesewas if i.id == item.id else int(i.line_total_pesewas)
        for i in active_items(order)
    ]
    subtotal, total = compute_totals(remaining, int(order.discount_pesewas))
    payload = ItemModified(
        line=LS(**line), subtotal_pesewas=subtotal, total_pesewas=total
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ITEM_MODIFIED,
                payload,
                order_id=order.id,
            )
        ],
        response={
            "id": str(order.id),
            "item": line,
            "subtotal_pesewas": subtotal,
            "total_pesewas": total,
        },
    )
