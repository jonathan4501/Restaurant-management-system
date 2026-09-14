"""
The order state machine. Enforced server-side; illegal transitions are a 409, never a coercion.

    DRAFT ─submit─► SUBMITTED ─ack─► PREPARING ─ready─► READY ─serve─► SERVED ─pay─► CLOSED
                       │                 │                                 │            │
                       │                 └── void (MANAGER PIN + reason) ──┼──► VOIDED  │
                       └── void (no PIN needed, nothing cooked yet) ───────┘            │
                                        reopen (MANAGER PIN + reason) ◄─────────────────┘

This table is the single source for "which command is legal in which status" and "which commands
need manager authorisation". Views and handlers consult it; they never re-encode it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from apps.core.errors import IllegalTransition
from apps.core.roles import AuthorisationPurpose

from .events import EventType
from .models import OrderItemStatus, OrderStatus


class OrderCommand(StrEnum):
    ADD_ITEM = "ADD_ITEM"
    REMOVE_ITEM = "REMOVE_ITEM"
    MODIFY_ITEM = "MODIFY_ITEM"
    SUBMIT = "SUBMIT"
    ACK = "ACK"
    START_ITEM = "START_ITEM"
    READY_ITEM = "READY_ITEM"
    READY = "READY"
    SERVE = "SERVE"
    FIRE = "FIRE"
    DISCOUNT = "DISCOUNT"
    COMP = "COMP"
    PRICE_OVERRIDE = "PRICE_OVERRIDE"
    VOID = "VOID"
    CLOSE = "CLOSE"
    REOPEN = "REOPEN"


@dataclass(frozen=True)
class Transition:
    to: OrderStatus
    emits: EventType
    authorisation: AuthorisationPurpose | None = None  # manager PIN + reason code required

    @property
    def requires_authorisation(self) -> bool:
        return self.authorisation is not None


S = OrderStatus
C = OrderCommand
E = EventType
P = AuthorisationPurpose

TRANSITIONS: dict[tuple[OrderStatus, OrderCommand], Transition] = {
    # building the draft
    (S.DRAFT, C.ADD_ITEM): Transition(S.DRAFT, E.ITEM_ADDED),
    (S.DRAFT, C.REMOVE_ITEM): Transition(S.DRAFT, E.ITEM_REMOVED),
    (S.DRAFT, C.MODIFY_ITEM): Transition(S.DRAFT, E.ITEM_MODIFIED),
    (S.DRAFT, C.SUBMIT): Transition(S.SUBMITTED, E.ORDER_SUBMITTED),
    (S.DRAFT, C.VOID): Transition(S.VOIDED, E.ORDER_VOIDED),
    # with the kitchen
    (S.SUBMITTED, C.ACK): Transition(S.PREPARING, E.KITCHEN_ACKNOWLEDGED),
    (S.SUBMITTED, C.START_ITEM): Transition(S.PREPARING, E.ITEM_STARTED),
    (S.SUBMITTED, C.READY): Transition(S.READY, E.ORDER_READY),  # drinks: straight to ready
    (S.SUBMITTED, C.FIRE): Transition(S.SUBMITTED, E.COURSE_FIRED),
    (S.SUBMITTED, C.VOID): Transition(S.VOIDED, E.ORDER_VOIDED),  # nothing cooked yet: no PIN
    (S.PREPARING, C.START_ITEM): Transition(S.PREPARING, E.ITEM_STARTED),
    (S.PREPARING, C.READY_ITEM): Transition(S.PREPARING, E.ITEM_READY),
    (S.PREPARING, C.READY): Transition(S.READY, E.ORDER_READY),
    (S.PREPARING, C.FIRE): Transition(S.PREPARING, E.COURSE_FIRED),
    (S.PREPARING, C.VOID): Transition(S.VOIDED, E.ORDER_VOIDED, P.VOID_AFTER_ACK),
    (S.READY, C.SERVE): Transition(S.SERVED, E.ORDER_SERVED),
    (S.READY, C.VOID): Transition(S.VOIDED, E.ORDER_VOIDED, P.VOID_AFTER_ACK),
    # served, waiting for the bill
    (S.SERVED, C.CLOSE): Transition(S.CLOSED, E.ORDER_CLOSED),  # only via session settlement
    (S.SERVED, C.VOID): Transition(S.VOIDED, E.ORDER_VOIDED, P.VOID_AFTER_ACK),
    # money adjustments: status unchanged, authorisation always
    (S.SUBMITTED, C.DISCOUNT): Transition(S.SUBMITTED, E.DISCOUNT_APPLIED, P.DISCOUNT),
    (S.PREPARING, C.DISCOUNT): Transition(S.PREPARING, E.DISCOUNT_APPLIED, P.DISCOUNT),
    (S.READY, C.DISCOUNT): Transition(S.READY, E.DISCOUNT_APPLIED, P.DISCOUNT),
    (S.SERVED, C.DISCOUNT): Transition(S.SERVED, E.DISCOUNT_APPLIED, P.DISCOUNT),
    (S.SUBMITTED, C.COMP): Transition(S.SUBMITTED, E.COMP_APPLIED, P.COMP),
    (S.PREPARING, C.COMP): Transition(S.PREPARING, E.COMP_APPLIED, P.COMP),
    (S.READY, C.COMP): Transition(S.READY, E.COMP_APPLIED, P.COMP),
    (S.SERVED, C.COMP): Transition(S.SERVED, E.COMP_APPLIED, P.COMP),
    (S.SUBMITTED, C.PRICE_OVERRIDE): Transition(S.SUBMITTED, E.PRICE_OVERRIDDEN, P.PRICE_OVERRIDE),
    (S.PREPARING, C.PRICE_OVERRIDE): Transition(S.PREPARING, E.PRICE_OVERRIDDEN, P.PRICE_OVERRIDE),
    (S.READY, C.PRICE_OVERRIDE): Transition(S.READY, E.PRICE_OVERRIDDEN, P.PRICE_OVERRIDE),
    (S.SERVED, C.PRICE_OVERRIDE): Transition(S.SERVED, E.PRICE_OVERRIDDEN, P.PRICE_OVERRIDE),
    # after the bill
    (S.CLOSED, C.REOPEN): Transition(S.SERVED, E.ORDER_REOPENED, P.REOPEN),
}

TERMINAL: frozenset[OrderStatus] = frozenset({S.VOIDED})


def transition(status: OrderStatus | str, command: OrderCommand | str) -> Transition:
    key = (OrderStatus(status), OrderCommand(command))
    try:
        return TRANSITIONS[key]
    except KeyError:
        raise IllegalTransition(f"Cannot {key[1].lower()} an order in status {key[0]}.") from None


def legal_commands(status: OrderStatus | str) -> set[OrderCommand]:
    s = OrderStatus(status)
    return {c for (st, c) in TRANSITIONS if st == s}


# ---- item-level statuses -------------------------------------------------------------------

IS = OrderItemStatus

ITEM_TRANSITIONS: dict[tuple[OrderItemStatus, OrderCommand], OrderItemStatus] = {
    (IS.PENDING, C.START_ITEM): IS.PREPARING,
    (IS.PENDING, C.READY_ITEM): IS.READY,
    (IS.PREPARING, C.READY_ITEM): IS.READY,
    (IS.PENDING, C.READY): IS.READY,
    (IS.PREPARING, C.READY): IS.READY,
    (IS.READY, C.SERVE): IS.SERVED,
    (IS.PENDING, C.VOID): IS.VOIDED,
    (IS.PREPARING, C.VOID): IS.VOIDED,
    (IS.READY, C.VOID): IS.VOIDED,
    (IS.SERVED, C.VOID): IS.VOIDED,
}


def item_transition(status: OrderItemStatus | str, command: OrderCommand | str) -> OrderItemStatus:
    key = (OrderItemStatus(status), OrderCommand(command))
    try:
        return ITEM_TRANSITIONS[key]
    except KeyError:
        raise IllegalTransition(f"Cannot {key[1].lower()} a line in status {key[0]}.") from None
