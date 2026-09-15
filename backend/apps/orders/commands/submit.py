"""Submit assigns business_date + order_number under OrderCounter row lock."""

from __future__ import annotations

import uuid

from django.utils import timezone

from apps.accounts.models import Restaurant
from apps.core.business_date import business_date
from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.roles import AggregateType
from apps.orders.commands._common import (
    active_items,
    assert_transition,
    item_to_line_dict,
    lock_order,
)
from apps.orders.events import EventType, LineSnapshot, OrderSubmitted
from apps.orders.models import OrderCounter
from apps.orders.state_machine import OrderCommand


def submit_order(ctx: CommandContext, order_id: uuid.UUID) -> CommandOutcome:
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.SUBMIT)

    items = active_items(order)
    if not items:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR, "Cannot submit an empty order.")

    restaurant = Restaurant.objects.get(pk=ctx.restaurant_id)
    bdate = business_date(timezone.now(), restaurant.timezone, int(restaurant.day_cutover_hour))

    counter, _ = OrderCounter.objects.select_for_update().get_or_create(
        business_date=bdate,
        defaults={"next_number": 1},
    )
    order_number = int(counter.next_number)
    counter.next_number = order_number + 1
    counter.save(update_fields=["next_number"])

    lines = [LineSnapshot(**item_to_line_dict(i)) for i in items]
    payload = OrderSubmitted(
        order_number=order_number,
        business_date=bdate.isoformat(),
        session_id=str(order.session_id),
        table_number=order.session.table.number,
        origin=order.origin,
        lines=lines,
        subtotal_pesewas=int(order.subtotal_pesewas),
        discount_pesewas=int(order.discount_pesewas),
        total_pesewas=int(order.total_pesewas),
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ORDER_SUBMITTED,
                payload,
                order_id=order.id,
            )
        ],
        response={
            "id": str(order.id),
            "status": "SUBMITTED",
            "order_number": order_number,
            "business_date": bdate.isoformat(),
            "session_id": str(order.session_id),
            "table_number": order.session.table.number,
            "origin": order.origin,
            "lines": [item_to_line_dict(i) for i in items],
            "subtotal_pesewas": int(order.subtotal_pesewas),
            "discount_pesewas": int(order.discount_pesewas),
            "total_pesewas": int(order.total_pesewas),
        },
    )
