"""
The event vocabulary (docs/03-data-model.md). One enum member and one frozen dataclass per event.
`test_every_event_has_a_payload_class` fails if the two drift apart.

Handlers build a payload dataclass and call .to_payload(); the runner stores the dict. Money in
payloads is integer pesewas like everywhere else.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, ClassVar

from apps.core.roles import AggregateType


class EventType(StrEnum):
    # ORDER
    ORDER_OPENED = "ORDER_OPENED"
    ITEM_ADDED = "ITEM_ADDED"
    ITEM_REMOVED = "ITEM_REMOVED"
    ITEM_MODIFIED = "ITEM_MODIFIED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    KITCHEN_ACKNOWLEDGED = "KITCHEN_ACKNOWLEDGED"
    ITEM_STARTED = "ITEM_STARTED"
    ITEM_READY = "ITEM_READY"
    ORDER_READY = "ORDER_READY"
    ORDER_SERVED = "ORDER_SERVED"
    COURSE_FIRED = "COURSE_FIRED"
    DISCOUNT_APPLIED = "DISCOUNT_APPLIED"
    COMP_APPLIED = "COMP_APPLIED"
    PRICE_OVERRIDDEN = "PRICE_OVERRIDDEN"
    ORDER_VOIDED = "ORDER_VOIDED"
    ORDER_CLOSED = "ORDER_CLOSED"
    ORDER_REOPENED = "ORDER_REOPENED"
    # SESSION
    SESSION_OPENED = "SESSION_OPENED"
    PAYMENT_RECORDED = "PAYMENT_RECORDED"
    PAYMENT_VOIDED = "PAYMENT_VOIDED"
    SESSION_SETTLED = "SESSION_SETTLED"
    SESSION_REOPENED = "SESSION_REOPENED"
    SESSION_CLOSED = "SESSION_CLOSED"
    RECEIPT_REQUESTED = "RECEIPT_REQUESTED"
    # SHIFT
    SHIFT_OPENED = "SHIFT_OPENED"
    DRAWER_MOVEMENT = "DRAWER_MOVEMENT"
    DRAWER_COUNTED = "DRAWER_COUNTED"
    SHIFT_CLOSED = "SHIFT_CLOSED"
    # MENU_ITEM
    ITEM_86ED = "ITEM_86ED"
    ITEM_RESTORED = "ITEM_RESTORED"
    PRICE_CHANGED = "PRICE_CHANGED"
    # DEVICE
    DEVICE_ENROLLED = "DEVICE_ENROLLED"
    DEVICE_REVOKED = "DEVICE_REVOKED"
    PIN_FAILED = "PIN_FAILED"
    PIN_LOCKED = "PIN_LOCKED"
    # STAFF
    MANAGER_AUTHORISED = "MANAGER_AUTHORISED"


AGGREGATE_OF: dict[EventType, AggregateType] = {
    **{
        e: AggregateType.ORDER
        for e in EventType
        if e.name.startswith(
            ("ORDER_", "ITEM_", "COURSE_", "DISCOUNT_", "COMP_", "PRICE_OVERRIDDEN", "KITCHEN_")
        )
    },
    **{
        e: AggregateType.SESSION
        for e in (
            EventType.SESSION_OPENED,
            EventType.PAYMENT_RECORDED,
            EventType.PAYMENT_VOIDED,
            EventType.SESSION_SETTLED,
            EventType.SESSION_REOPENED,
            EventType.SESSION_CLOSED,
            EventType.RECEIPT_REQUESTED,
        )
    },
    **{
        e: AggregateType.SHIFT
        for e in (
            EventType.SHIFT_OPENED,
            EventType.DRAWER_MOVEMENT,
            EventType.DRAWER_COUNTED,
            EventType.SHIFT_CLOSED,
        )
    },
    **{
        e: AggregateType.MENU_ITEM
        for e in (EventType.ITEM_86ED, EventType.ITEM_RESTORED, EventType.PRICE_CHANGED)
    },
    **{
        e: AggregateType.DEVICE
        for e in (
            EventType.DEVICE_ENROLLED,
            EventType.DEVICE_REVOKED,
            EventType.PIN_FAILED,
            EventType.PIN_LOCKED,
        )
    },
    EventType.MANAGER_AUTHORISED: AggregateType.STAFF,
}

# Rendered visually distinct in the owner's log. Derived from type, never stored.
FLAGGED: frozenset[EventType] = frozenset(
    {
        EventType.ORDER_VOIDED,
        EventType.DISCOUNT_APPLIED,
        EventType.COMP_APPLIED,
        EventType.PRICE_OVERRIDDEN,
        EventType.ORDER_REOPENED,
        EventType.SESSION_REOPENED,
        EventType.PAYMENT_VOIDED,
        EventType.DRAWER_MOVEMENT,
        EventType.PIN_FAILED,
        EventType.PIN_LOCKED,
        EventType.PRICE_CHANGED,
    }
)


def is_flagged(event_type: str, payload: dict[str, Any] | None = None) -> bool:
    """ORDER_VOIDED is flagged only after the kitchen acknowledged (payload.status_at_void)."""
    try:
        et = EventType(event_type)
    except ValueError:
        return False
    if et is EventType.ORDER_VOIDED:
        return (payload or {}).get("status_at_void") not in (None, "DRAFT", "SUBMITTED")
    return et in FLAGGED


# ------------------------------------------------------------------ payloads

PAYLOADS: dict[EventType, type[Payload]] = {}


@dataclass(frozen=True)
class Payload:
    event_type: ClassVar[EventType]

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def payload(event_type: EventType) -> Any:
    def register(cls: type[Payload]) -> type[Payload]:
        cls.event_type = event_type
        PAYLOADS[event_type] = cls
        return cls

    return register


@dataclass(frozen=True)
class LineSnapshot:
    item_id: str
    menu_item_id: str
    name: str
    unit_price_pesewas: int
    prep_station: str
    quantity: int
    modifiers: list[dict[str, Any]]
    notes: str
    course: int
    line_total_pesewas: int


# ---- ORDER
@payload(EventType.ORDER_OPENED)
@dataclass(frozen=True)
class OrderOpened(Payload):
    session_id: str
    table_number: str
    origin: str


@payload(EventType.ITEM_ADDED)
@dataclass(frozen=True)
class ItemAdded(Payload):
    line: LineSnapshot
    subtotal_pesewas: int
    total_pesewas: int


@payload(EventType.ITEM_REMOVED)
@dataclass(frozen=True)
class ItemRemoved(Payload):
    item_id: str
    subtotal_pesewas: int
    total_pesewas: int


@payload(EventType.ITEM_MODIFIED)
@dataclass(frozen=True)
class ItemModified(Payload):
    line: LineSnapshot
    subtotal_pesewas: int
    total_pesewas: int


@payload(EventType.ORDER_SUBMITTED)
@dataclass(frozen=True)
class OrderSubmitted(Payload):
    order_number: int
    business_date: str
    session_id: str
    table_number: str
    origin: str
    lines: list[LineSnapshot]
    subtotal_pesewas: int
    discount_pesewas: int
    total_pesewas: int


@payload(EventType.KITCHEN_ACKNOWLEDGED)
@dataclass(frozen=True)
class KitchenAcknowledged(Payload):
    order_number: int


@payload(EventType.ITEM_STARTED)
@dataclass(frozen=True)
class ItemStarted(Payload):
    item_id: str
    order_number: int


@payload(EventType.ITEM_READY)
@dataclass(frozen=True)
class ItemReady(Payload):
    item_id: str
    order_number: int


@payload(EventType.ORDER_READY)
@dataclass(frozen=True)
class OrderReady(Payload):
    order_number: int
    table_number: str
    seconds_since_acknowledged: int | None


@payload(EventType.ORDER_SERVED)
@dataclass(frozen=True)
class OrderServed(Payload):
    order_number: int
    table_number: str


@payload(EventType.COURSE_FIRED)
@dataclass(frozen=True)
class CourseFired(Payload):
    order_number: int
    course: int


@payload(EventType.DISCOUNT_APPLIED)
@dataclass(frozen=True)
class DiscountApplied(Payload):
    kind: str  # PERCENT | AMOUNT
    value: int  # percent (0..100) or pesewas
    amount_pesewas: int
    subtotal_pesewas: int
    total_pesewas: int
    note: str = ""


@payload(EventType.COMP_APPLIED)
@dataclass(frozen=True)
class CompApplied(Payload):
    amount_pesewas: int
    subtotal_pesewas: int
    total_pesewas: int
    note: str = ""


@payload(EventType.PRICE_OVERRIDDEN)
@dataclass(frozen=True)
class PriceOverridden(Payload):
    item_id: str
    old_unit_price_pesewas: int
    new_unit_price_pesewas: int
    subtotal_pesewas: int
    total_pesewas: int
    note: str = ""


@payload(EventType.ORDER_VOIDED)
@dataclass(frozen=True)
class OrderVoided(Payload):
    order_number: int | None
    status_at_void: str
    total_pesewas: int
    note: str = ""


@payload(EventType.ORDER_CLOSED)
@dataclass(frozen=True)
class OrderClosed(Payload):
    order_number: int
    session_id: str
    total_pesewas: int


@payload(EventType.ORDER_REOPENED)
@dataclass(frozen=True)
class OrderReopened(Payload):
    order_number: int
    session_id: str
    note: str = ""


# ---- SESSION
@payload(EventType.SESSION_OPENED)
@dataclass(frozen=True)
class SessionOpened(Payload):
    table_id: str
    table_number: str
    party_size: int | None


@payload(EventType.PAYMENT_RECORDED)
@dataclass(frozen=True)
class PaymentRecorded(Payload):
    payment_id: str
    shift_id: str
    method: str
    amount_pesewas: int
    tendered_pesewas: int | None
    change_pesewas: int | None
    external_reference: str | None
    order_id: str | None
    bill_total_pesewas: int
    paid_pesewas: int
    balance_pesewas: int


@payload(EventType.PAYMENT_VOIDED)
@dataclass(frozen=True)
class PaymentVoided(Payload):
    payment_id: str
    amount_pesewas: int
    method: str
    balance_pesewas: int
    note: str = ""


@payload(EventType.SESSION_SETTLED)
@dataclass(frozen=True)
class SessionSettled(Payload):
    table_number: str
    bill_total_pesewas: int
    paid_pesewas: int
    order_ids: list[str]
    payments: list[dict[str, Any]] = field(default_factory=list)


@payload(EventType.SESSION_REOPENED)
@dataclass(frozen=True)
class SessionReopened(Payload):
    table_number: str
    order_ids: list[str]
    note: str = ""


@payload(EventType.SESSION_CLOSED)
@dataclass(frozen=True)
class SessionClosed(Payload):
    table_number: str
    bill_total_pesewas: int
    paid_pesewas: int


@payload(EventType.RECEIPT_REQUESTED)
@dataclass(frozen=True)
class ReceiptRequested(Payload):
    table_number: str
    reprint: bool


# ---- SHIFT
@payload(EventType.SHIFT_OPENED)
@dataclass(frozen=True)
class ShiftOpened(Payload):
    cashier_id: str
    opening_float_pesewas: int


@payload(EventType.DRAWER_MOVEMENT)
@dataclass(frozen=True)
class DrawerMovement(Payload):
    movement_id: str
    kind: str  # NO_SALE | PAID_OUT | PAID_IN
    amount_pesewas: int
    note: str = ""


@payload(EventType.DRAWER_COUNTED)
@dataclass(frozen=True)
class DrawerCounted(Payload):
    declared_cash_pesewas: int
    expected_cash_pesewas: int
    variance_pesewas: int


@payload(EventType.SHIFT_CLOSED)
@dataclass(frozen=True)
class ShiftClosed(Payload):
    cashier_id: str
    opening_float_pesewas: int
    cash_payments_pesewas: int
    paid_out_pesewas: int
    paid_in_pesewas: int
    expected_cash_pesewas: int
    declared_cash_pesewas: int
    variance_pesewas: int
    totals_by_method: dict[str, int]
    note: str = ""


# ---- MENU_ITEM
@payload(EventType.ITEM_86ED)
@dataclass(frozen=True)
class Item86ed(Payload):
    menu_item_id: str
    name: str


@payload(EventType.ITEM_RESTORED)
@dataclass(frozen=True)
class ItemRestored(Payload):
    menu_item_id: str
    name: str


@payload(EventType.PRICE_CHANGED)
@dataclass(frozen=True)
class PriceChanged(Payload):
    menu_item_id: str
    name: str
    old_price_pesewas: int
    new_price_pesewas: int
    during_service: bool


# ---- DEVICE
@payload(EventType.DEVICE_ENROLLED)
@dataclass(frozen=True)
class DeviceEnrolled(Payload):
    label: str
    allowed_roles: list[str]


@payload(EventType.DEVICE_REVOKED)
@dataclass(frozen=True)
class DeviceRevoked(Payload):
    label: str
    note: str = ""


@payload(EventType.PIN_FAILED)
@dataclass(frozen=True)
class PinFailed(Payload):
    staff_id: str | None
    attempt: int


@payload(EventType.PIN_LOCKED)
@dataclass(frozen=True)
class PinLocked(Payload):
    lockout_seconds: int


# ---- STAFF
@payload(EventType.MANAGER_AUTHORISED)
@dataclass(frozen=True)
class ManagerAuthorised(Payload):
    purpose: str
    for_device_id: str | None
