"""Projections for MENU_ITEM events. is_available / price_pesewas are derived from the stream."""

from apps.core.projections import project
from apps.menu.cache import invalidate_menu_cache
from apps.menu.models import MenuItem
from apps.orders.events import EventType
from apps.orders.models import OrderEvent


@project(EventType.ITEM_86ED)
def item_86ed(event: OrderEvent) -> None:
    MenuItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(is_available=False)
    invalidate_menu_cache(event.restaurant_id)


@project(EventType.ITEM_RESTORED)
def item_restored(event: OrderEvent) -> None:
    MenuItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(is_available=True)
    invalidate_menu_cache(event.restaurant_id)


@project(EventType.PRICE_CHANGED)
def price_changed(event: OrderEvent) -> None:
    MenuItem.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(price_pesewas=int(event.payload["new_price_pesewas"]))
    invalidate_menu_cache(event.restaurant_id)
