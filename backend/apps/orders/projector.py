"""
Projections for ORDER events. WS03 fills these in; the registry and the rebuild/verify commands
already route every event here. Rules: deterministic, no clock (use event.created_at), no reads
from menu_items (the payload carries the snapshots).
"""

from apps.core.projections import project
from apps.orders.events import EventType
from apps.orders.models import OrderEvent


@project(EventType.ORDER_OPENED)
def order_opened(event: OrderEvent) -> None:
    raise NotImplementedError("WS03: create the Order projection row from ORDER_OPENED")


@project(
    EventType.ITEM_ADDED,
    EventType.ITEM_REMOVED,
    EventType.ITEM_MODIFIED,
    EventType.ORDER_SUBMITTED,
    EventType.KITCHEN_ACKNOWLEDGED,
    EventType.ITEM_STARTED,
    EventType.ITEM_READY,
    EventType.ORDER_READY,
    EventType.ORDER_SERVED,
    EventType.COURSE_FIRED,
    EventType.DISCOUNT_APPLIED,
    EventType.COMP_APPLIED,
    EventType.PRICE_OVERRIDDEN,
    EventType.ORDER_VOIDED,
    EventType.ORDER_CLOSED,
    EventType.ORDER_REOPENED,
)
def order_event(event: OrderEvent) -> None:
    raise NotImplementedError(f"WS03: project {event.event_type} onto orders / order_items")
