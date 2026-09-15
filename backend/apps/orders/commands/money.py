"""Void, discount, comp, price override."""

from __future__ import annotations

import uuid
from typing import Any

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.money import require_pesewas
from apps.core.roles import AggregateType
from apps.orders.commands._common import (
    active_items,
    assert_transition,
    compute_totals,
    lock_order,
)
from apps.orders.events import (
    CompApplied,
    DiscountApplied,
    EventType,
    OrderVoided,
    PriceOverridden,
)
from apps.orders.models import OrderItem
from apps.orders.state_machine import OrderCommand
from apps.orders.totals import apply_percent_discount, line_total


def void_order(ctx: CommandContext, order_id: uuid.UUID, data: dict[str, Any]) -> CommandOutcome:
    order = lock_order(order_id)
    t = assert_transition(order, OrderCommand.VOID)
    if t.requires_authorisation and ctx.authorised_by is None:
        raise ApiError(
            403,
            ErrorCode.AUTHORISATION_REQUIRED,
            "Voiding after kitchen acknowledgement needs manager authorisation.",
        )

    reason = ctx.reason_code or data.get("reason_code")
    if not reason:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "reason_code is required to void an order.",
            errors={"reason_code": ["Required."]},
        )

    payload = OrderVoided(
        order_number=order.order_number,
        status_at_void=order.status,
        total_pesewas=int(order.total_pesewas),
        note=data.get("note") or "",
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ORDER_VOIDED,
                payload,
                order_id=order.id,
                reason_code=reason,
            )
        ],
        response={
            "id": str(order.id),
            "status": "VOIDED",
            "status_at_void": order.status,
            "total_pesewas": int(order.total_pesewas),
            "reason_code": reason,
        },
    )


def apply_discount(
    ctx: CommandContext, order_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.DISCOUNT)
    if ctx.authorised_by is None:
        raise ApiError(
            403, ErrorCode.AUTHORISATION_REQUIRED, "Discount needs manager authorisation."
        )

    kind = data["kind"]
    value = int(data["value"])
    subtotal = int(order.subtotal_pesewas)
    if kind == "PERCENT":
        amount = apply_percent_discount(subtotal, value)
    elif kind == "AMOUNT":
        amount = value
    else:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "kind must be PERCENT or AMOUNT.",
            errors={"kind": ["Invalid."]},
        )

    if amount > subtotal:
        raise ApiError(
            422,
            ErrorCode.DISCOUNT_EXCEEDS_SUBTOTAL,
            "Discount cannot exceed the order subtotal.",
        )

    total = max(0, subtotal - amount)
    payload = DiscountApplied(
        kind=kind,
        value=value,
        amount_pesewas=amount,
        subtotal_pesewas=subtotal,
        total_pesewas=total,
        note=data.get("note") or "",
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.DISCOUNT_APPLIED,
                payload,
                order_id=order.id,
            )
        ],
        response={
            "id": str(order.id),
            "discount_pesewas": amount,
            "subtotal_pesewas": subtotal,
            "total_pesewas": total,
        },
    )


def apply_comp(ctx: CommandContext, order_id: uuid.UUID, data: dict[str, Any]) -> CommandOutcome:
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.COMP)
    if ctx.authorised_by is None:
        raise ApiError(403, ErrorCode.AUTHORISATION_REQUIRED, "Comp needs manager authorisation.")

    subtotal = int(order.subtotal_pesewas)
    amount = subtotal
    payload = CompApplied(
        amount_pesewas=amount,
        subtotal_pesewas=subtotal,
        total_pesewas=0,
        note=data.get("note") or "",
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.COMP_APPLIED,
                payload,
                order_id=order.id,
            )
        ],
        response={
            "id": str(order.id),
            "kind": "COMP",
            "discount_pesewas": amount,
            "subtotal_pesewas": subtotal,
            "total_pesewas": 0,
        },
    )


def price_override(
    ctx: CommandContext, order_id: uuid.UUID, item_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.PRICE_OVERRIDE)
    if ctx.authorised_by is None:
        raise ApiError(
            403, ErrorCode.AUTHORISATION_REQUIRED, "Price override needs manager authorisation."
        )

    try:
        item = OrderItem.objects.select_for_update().get(pk=item_id, order_id=order.id)
    except OrderItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order item not found.") from err

    try:
        new_unit = require_pesewas(data["unit_price_pesewas"])
    except ValueError as err:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            str(err),
            errors={"unit_price_pesewas": [str(err)]},
        ) from err

    old_unit = int(item.unit_price_pesewas)
    mod_prices = [int(m.get("price_pesewas", 0)) for m in (item.modifiers or [])]
    new_line_total = line_total(new_unit, mod_prices, int(item.quantity))

    line_totals = [
        new_line_total if i.id == item.id else int(i.line_total_pesewas)
        for i in active_items(order)
    ]
    subtotal, total = compute_totals(line_totals, int(order.discount_pesewas))

    payload = PriceOverridden(
        item_id=str(item.id),
        old_unit_price_pesewas=old_unit,
        new_unit_price_pesewas=new_unit,
        subtotal_pesewas=subtotal,
        total_pesewas=total,
        note=data.get("note") or "",
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.PRICE_OVERRIDDEN,
                payload,
                order_id=order.id,
            )
        ],
        response={
            "id": str(order.id),
            "item_id": str(item.id),
            "old_unit_price_pesewas": old_unit,
            "new_unit_price_pesewas": new_unit,
            "subtotal_pesewas": subtotal,
            "total_pesewas": total,
        },
    )
