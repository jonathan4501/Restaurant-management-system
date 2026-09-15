"""Cashier / floor state chip for an open table session."""

from __future__ import annotations

from apps.orders.models import Order, OrderStatus


def session_state_chip(
    *, statuses: list[str], paid_pesewas: int, bill_total_pesewas: int
) -> str | None:
    """
    sent / cooking / food_ready / ready_to_pay / part_paid.

    Priority matches the cashier board: money first, then food readiness.
    """
    balance = bill_total_pesewas - paid_pesewas
    active = [s for s in statuses if s != OrderStatus.VOIDED]
    if paid_pesewas > 0 and balance > 0:
        return "part_paid"
    if any(s == OrderStatus.READY for s in active):
        return "food_ready"
    if any(s == OrderStatus.PREPARING for s in active):
        return "cooking"
    if any(s == OrderStatus.SUBMITTED for s in active):
        return "sent"
    if any(s == OrderStatus.SERVED for s in active) and balance > 0:
        return "ready_to_pay"
    if (
        active
        and all(s in (OrderStatus.SERVED, OrderStatus.CLOSED) for s in active)
        and balance > 0
    ):
        return "ready_to_pay"
    return None


def chip_for_session(session_id) -> str | None:
    statuses = list(Order.objects.filter(session_id=session_id).values_list("status", flat=True))
    from apps.floor.models import TableSession

    session = TableSession.objects.get(pk=session_id)
    return session_state_chip(
        statuses=statuses,
        paid_pesewas=int(session.paid_pesewas),
        bill_total_pesewas=int(session.bill_total_pesewas),
    )
