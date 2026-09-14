"""Menu command handlers. Projection tables are updated by the projector, not here."""

from __future__ import annotations

import uuid

from apps.accounts.models import Restaurant
from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.money import require_pesewas
from apps.core.roles import AggregateType
from apps.menu.models import MenuItem
from apps.menu.service_hours import is_during_service
from apps.orders.events import EventType, Item86ed, ItemRestored, PriceChanged


def _get_item_for_update(item_id: uuid.UUID) -> MenuItem:
    try:
        return MenuItem.objects.select_for_update().get(pk=item_id, is_active=True)
    except MenuItem.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Menu item not found.") from err


def eighty_six(ctx: CommandContext, item_id: uuid.UUID) -> CommandOutcome:
    del ctx  # restaurant context already set by middleware / runner
    item = _get_item_for_update(item_id)
    payload = Item86ed(menu_item_id=str(item.id), name=item.name).to_payload()
    # Stream clients drop the item without a menu refetch. Request to WS00: add is_available
    # to Item86ed / ItemRestored dataclasses; included here until then.
    payload["is_available"] = False
    draft = EventDraft(
        AggregateType.MENU_ITEM,
        item.id,
        EventType.ITEM_86ED,
        payload,
    )
    return CommandOutcome(
        events=[draft],
        response={
            "menu_item_id": str(item.id),
            "name": item.name,
            "is_available": False,
        },
    )


def restore(ctx: CommandContext, item_id: uuid.UUID) -> CommandOutcome:
    del ctx
    item = _get_item_for_update(item_id)
    payload = ItemRestored(menu_item_id=str(item.id), name=item.name).to_payload()
    payload["is_available"] = True
    draft = EventDraft(
        AggregateType.MENU_ITEM,
        item.id,
        EventType.ITEM_RESTORED,
        payload,
    )
    return CommandOutcome(
        events=[draft],
        response={
            "menu_item_id": str(item.id),
            "name": item.name,
            "is_available": True,
        },
    )


def change_price(
    ctx: CommandContext, item_id: uuid.UUID, new_price_pesewas: int, *, during_service: bool
) -> CommandOutcome:
    del ctx
    item = _get_item_for_update(item_id)
    try:
        new_price = require_pesewas(new_price_pesewas)
    except ValueError as err:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            str(err),
            errors={"price_pesewas": [str(err)]},
        ) from err

    old_price = int(item.price_pesewas)
    payload = PriceChanged(
        menu_item_id=str(item.id),
        name=item.name,
        old_price_pesewas=old_price,
        new_price_pesewas=new_price,
        during_service=during_service,
    ).to_payload()
    draft = EventDraft(
        AggregateType.MENU_ITEM,
        item.id,
        EventType.PRICE_CHANGED,
        payload,
    )
    return CommandOutcome(
        events=[draft],
        response={
            "menu_item_id": str(item.id),
            "name": item.name,
            "old_price_pesewas": old_price,
            "new_price_pesewas": new_price,
            "during_service": during_service,
        },
    )


def price_change_during_service(restaurant_id: uuid.UUID) -> bool:
    """Look up the restaurant and report whether we are inside service hours."""
    restaurant = Restaurant.objects.filter(pk=restaurant_id).first()
    if restaurant is None:
        return True  # fail closed
    return is_during_service(restaurant)
