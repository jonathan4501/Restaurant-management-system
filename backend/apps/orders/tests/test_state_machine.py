"""Every (status, command) pair is asserted: either the expected transition or IllegalTransition."""

from __future__ import annotations

import pytest

from apps.core.errors import IllegalTransition
from apps.core.roles import AuthorisationPurpose as P
from apps.orders.events import EventType as E
from apps.orders.models import OrderItemStatus as IS
from apps.orders.models import OrderStatus as S
from apps.orders.state_machine import (
    ITEM_TRANSITIONS,
    TRANSITIONS,
    item_transition,
    legal_commands,
    transition,
)
from apps.orders.state_machine import (
    OrderCommand as C,
)

# The expected table, spelled out so a change to the state machine must be made twice on purpose.
EXPECTED: dict[tuple[S, C], tuple[S, E, P | None]] = {
    (S.DRAFT, C.ADD_ITEM): (S.DRAFT, E.ITEM_ADDED, None),
    (S.DRAFT, C.REMOVE_ITEM): (S.DRAFT, E.ITEM_REMOVED, None),
    (S.DRAFT, C.MODIFY_ITEM): (S.DRAFT, E.ITEM_MODIFIED, None),
    (S.DRAFT, C.SUBMIT): (S.SUBMITTED, E.ORDER_SUBMITTED, None),
    (S.DRAFT, C.VOID): (S.VOIDED, E.ORDER_VOIDED, None),
    (S.SUBMITTED, C.ACK): (S.PREPARING, E.KITCHEN_ACKNOWLEDGED, None),
    (S.SUBMITTED, C.START_ITEM): (S.PREPARING, E.ITEM_STARTED, None),
    (S.SUBMITTED, C.READY): (S.READY, E.ORDER_READY, None),
    (S.SUBMITTED, C.FIRE): (S.SUBMITTED, E.COURSE_FIRED, None),
    (S.SUBMITTED, C.VOID): (S.VOIDED, E.ORDER_VOIDED, None),
    (S.PREPARING, C.START_ITEM): (S.PREPARING, E.ITEM_STARTED, None),
    (S.PREPARING, C.READY_ITEM): (S.PREPARING, E.ITEM_READY, None),
    (S.PREPARING, C.READY): (S.READY, E.ORDER_READY, None),
    (S.PREPARING, C.FIRE): (S.PREPARING, E.COURSE_FIRED, None),
    (S.PREPARING, C.VOID): (S.VOIDED, E.ORDER_VOIDED, P.VOID_AFTER_ACK),
    (S.READY, C.SERVE): (S.SERVED, E.ORDER_SERVED, None),
    (S.READY, C.VOID): (S.VOIDED, E.ORDER_VOIDED, P.VOID_AFTER_ACK),
    (S.SERVED, C.CLOSE): (S.CLOSED, E.ORDER_CLOSED, None),
    (S.SERVED, C.VOID): (S.VOIDED, E.ORDER_VOIDED, P.VOID_AFTER_ACK),
    (S.CLOSED, C.REOPEN): (S.SERVED, E.ORDER_REOPENED, P.REOPEN),
}
for _status in (S.SUBMITTED, S.PREPARING, S.READY, S.SERVED):
    EXPECTED[(_status, C.DISCOUNT)] = (_status, E.DISCOUNT_APPLIED, P.DISCOUNT)
    EXPECTED[(_status, C.COMP)] = (_status, E.COMP_APPLIED, P.COMP)
    EXPECTED[(_status, C.PRICE_OVERRIDE)] = (_status, E.PRICE_OVERRIDDEN, P.PRICE_OVERRIDE)


@pytest.mark.parametrize("status", list(S))
@pytest.mark.parametrize("command", list(C))
def test_every_pair(status: S, command: C) -> None:
    if (status, command) in EXPECTED:
        to, emits, auth = EXPECTED[(status, command)]
        t = transition(status, command)
        assert (t.to, t.emits, t.authorisation) == (to, emits, auth)
    else:
        with pytest.raises(IllegalTransition):
            transition(status, command)


def test_table_and_expectations_are_the_same_set() -> None:
    assert set(TRANSITIONS) == set(EXPECTED)


def test_voided_is_terminal() -> None:
    assert legal_commands(S.VOIDED) == set()


def test_void_needs_no_pin_before_the_kitchen_touches_it_and_a_pin_after() -> None:
    assert transition(S.SUBMITTED, C.VOID).requires_authorisation is False
    assert transition(S.PREPARING, C.VOID).requires_authorisation is True
    assert transition(S.SERVED, C.VOID).requires_authorisation is True


def test_money_adjustments_always_need_authorisation() -> None:
    for (status, command), t in TRANSITIONS.items():
        if command in (C.DISCOUNT, C.COMP, C.PRICE_OVERRIDE, C.REOPEN):
            assert t.requires_authorisation, (status, command)


def test_cannot_serve_before_ready_or_pay_before_served() -> None:
    with pytest.raises(IllegalTransition):
        transition(S.PREPARING, C.SERVE)
    with pytest.raises(IllegalTransition):
        transition(S.READY, C.CLOSE)


def test_accepts_plain_strings() -> None:
    assert transition("DRAFT", "SUBMIT").to == S.SUBMITTED


@pytest.mark.parametrize("status", list(IS))
@pytest.mark.parametrize("command", list(C))
def test_every_item_pair(status: IS, command: C) -> None:
    if (status, command) in ITEM_TRANSITIONS:
        assert item_transition(status, command) == ITEM_TRANSITIONS[(status, command)]
    else:
        with pytest.raises(IllegalTransition):
            item_transition(status, command)


def test_item_lifecycle() -> None:
    assert item_transition(IS.PENDING, C.START_ITEM) == IS.PREPARING
    assert item_transition(IS.PREPARING, C.READY_ITEM) == IS.READY
    assert item_transition(IS.READY, C.SERVE) == IS.SERVED
    with pytest.raises(IllegalTransition):
        item_transition(IS.SERVED, C.READY_ITEM)
