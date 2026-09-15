"""Kitchen ack / start / ready and serve."""

from __future__ import annotations

import uuid

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.roles import AggregateType
from apps.orders.commands._common import active_items, assert_transition, lock_order
from apps.orders.events import (
    EventType,
    ItemReady,
    ItemStarted,
    KitchenAcknowledged,
    OrderReady,
    OrderServed,
)
from apps.orders.models import OrderItem, OrderItemStatus
from apps.orders.state_machine import OrderCommand, item_transition


def ack_order(ctx: CommandContext, order_id: uuid.UUID) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.ACK)
    if order.order_number is None:
        raise ApiError(409, ErrorCode.ILLEGAL_TRANSITION, "Order has no number yet.")

    payload = KitchenAcknowledged(order_number=int(order.order_number)).to_payload()
    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.KITCHEN_ACKNOWLEDGED,
                payload,
                order_id=order.id,
            )
        ],
        response={"id": str(order.id), "status": "PREPARING"},
    )


def start_item(ctx: CommandContext, order_id: uuid.UUID, item_id: uuid.UUID) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.START_ITEM)
    try:
        item = OrderItem.objects.select_for_update().get(pk=item_id, order_id=order.id)
    except OrderItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order item not found.") from err
    item_transition(item.status, OrderCommand.START_ITEM)

    payload = ItemStarted(
        item_id=str(item.id), order_number=int(order.order_number or 0)
    ).to_payload()
    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ITEM_STARTED,
                payload,
                order_id=order.id,
            )
        ],
        response={"id": str(order.id), "item_id": str(item.id), "item_status": "PREPARING"},
    )


def ready_item(ctx: CommandContext, order_id: uuid.UUID, item_id: uuid.UUID) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.READY_ITEM)
    try:
        item = OrderItem.objects.select_for_update().get(pk=item_id, order_id=order.id)
    except OrderItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order item not found.") from err
    item_transition(item.status, OrderCommand.READY_ITEM)

    events = [
        EventDraft(
            AggregateType.ORDER,
            order.id,
            EventType.ITEM_READY,
            ItemReady(item_id=str(item.id), order_number=int(order.order_number or 0)).to_payload(),
            order_id=order.id,
        )
    ]

    # After this item, would all active items be READY?
    others = [
        i for i in active_items(order) if i.id != item.id and i.status != OrderItemStatus.READY
    ]
    # Current item becomes READY via projector; treat it as ready for the check.
    if not others:
        seconds = None
        if order.acknowledged_at is not None:
            # created_at filled by runner; use 0 placeholder — projector uses event time
            seconds = 0
        events.append(
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ORDER_READY,
                OrderReady(
                    order_number=int(order.order_number or 0),
                    table_number=order.session.table.number,
                    seconds_since_acknowledged=seconds,
                ).to_payload(),
                order_id=order.id,
            )
        )

    return CommandOutcome(
        events=events,
        response={"id": str(order.id), "item_id": str(item.id), "item_status": "READY"},
    )


def ready_order(ctx: CommandContext, order_id: uuid.UUID) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.READY)
    seconds = None
    payload = OrderReady(
        order_number=int(order.order_number or 0),
        table_number=order.session.table.number,
        seconds_since_acknowledged=seconds,
    ).to_payload()
    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ORDER_READY,
                payload,
                order_id=order.id,
            )
        ],
        response={"id": str(order.id), "status": "READY"},
    )


def serve_order(ctx: CommandContext, order_id: uuid.UUID) -> CommandOutcome:
    del ctx
    order = lock_order(order_id)
    assert_transition(order, OrderCommand.SERVE)
    payload = OrderServed(
        order_number=int(order.order_number or 0),
        table_number=order.session.table.number,
    ).to_payload()
    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ORDER_SERVED,
                payload,
                order_id=order.id,
            )
        ],
        response={"id": str(order.id), "status": "SERVED"},
    )
