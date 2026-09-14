"""Which roles see which aggregate types on the stream. Guests have no stream at all."""

from typing import Any

from apps.core.roles import ActorRole, AggregateType, DeviceRole

_VISIBLE: dict[str, frozenset[str]] = {
    ActorRole.KITCHEN: frozenset({AggregateType.ORDER, AggregateType.MENU_ITEM}),
    ActorRole.WAITER: frozenset(
        {AggregateType.ORDER, AggregateType.SESSION, AggregateType.MENU_ITEM}
    ),
    ActorRole.CASHIER: frozenset(
        {AggregateType.ORDER, AggregateType.SESSION, AggregateType.SHIFT, AggregateType.MENU_ITEM}
    ),
    ActorRole.MANAGER: frozenset(AggregateType),
    ActorRole.OWNER: frozenset(AggregateType),
    DeviceRole.PRINTER: frozenset({AggregateType.ORDER, AggregateType.SESSION}),
}


def visible_to(role: str, envelope: dict[str, Any]) -> bool:
    allowed = _VISIBLE.get(str(role))
    return allowed is not None and envelope.get("aggregate_type") in allowed
