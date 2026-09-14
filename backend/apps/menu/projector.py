"""Projections for MENU_ITEM events. is_available is derived from ITEM_86ED / ITEM_RESTORED."""

from apps.core.projections import project
from apps.orders.events import EventType
from apps.orders.models import OrderEvent

from .models import MenuItem


@project(EventType.ITEM_86ED)
def item_86ed(event: OrderEvent) -> None:
    MenuItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(is_available=False)


@project(EventType.ITEM_RESTORED)
def item_restored(event: OrderEvent) -> None:
    MenuItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(is_available=True)


@project(EventType.PRICE_CHANGED)
def price_changed(event: OrderEvent) -> None:
    MenuItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(price_pesewas=int(event.payload["new_price_pesewas"]))
