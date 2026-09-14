"""Enumerations shared by every app. Values are stored in the database; never rename a member."""

from enum import StrEnum


class StaffRole(StrEnum):
    WAITER = "WAITER"
    KITCHEN = "KITCHEN"
    CASHIER = "CASHIER"
    MANAGER = "MANAGER"
    OWNER = "OWNER"


class ActorRole(StrEnum):
    """Who did a thing. Superset of StaffRole."""

    WAITER = "WAITER"
    KITCHEN = "KITCHEN"
    CASHIER = "CASHIER"
    MANAGER = "MANAGER"
    OWNER = "OWNER"
    GUEST = "GUEST"
    SYSTEM = "SYSTEM"


class DeviceRole(StrEnum):
    """Roles a device may host. PRINTER is the Raspberry Pi bridge (WS12)."""

    WAITER = "WAITER"
    KITCHEN = "KITCHEN"
    CASHIER = "CASHIER"
    MANAGER = "MANAGER"
    OWNER = "OWNER"
    GUEST = "GUEST"
    PRINTER = "PRINTER"


class AggregateType(StrEnum):
    ORDER = "ORDER"
    SESSION = "SESSION"
    SHIFT = "SHIFT"
    MENU_ITEM = "MENU_ITEM"
    DEVICE = "DEVICE"
    STAFF = "STAFF"


class AuthorisationPurpose(StrEnum):
    """What a manager authorisation token was issued for. A token is valid for one purpose only."""

    VOID_AFTER_ACK = "VOID_AFTER_ACK"
    DISCOUNT = "DISCOUNT"
    COMP = "COMP"
    PRICE_OVERRIDE = "PRICE_OVERRIDE"
    REOPEN = "REOPEN"
    DRAWER_MOVEMENT = "DRAWER_MOVEMENT"
    PAYMENT_VOID = "PAYMENT_VOID"
    PRICE_CHANGE_IN_SERVICE = "PRICE_CHANGE_IN_SERVICE"


MANAGER_ROLES = frozenset({ActorRole.MANAGER, ActorRole.OWNER})
STAFF_ROLES = frozenset(ActorRole(r.value) for r in StaffRole)


def choices(enum: type[StrEnum]) -> list[tuple[str, str]]:
    return [(m.value, m.value) for m in enum]
