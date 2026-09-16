"""Read models for the cashier: the open-bills board and the Z-report at shift close."""

from __future__ import annotations

import uuid
from typing import Any

from apps.floor.models import TableSession
from apps.floor.state_chip import chip_for_session
from apps.orders.models import Order, OrderStatus
from apps.payments.commands import shift_totals
from apps.payments.models import DrawerMovement, Payment, Shift


def serialize_shift(shift: Shift) -> dict[str, Any]:
    return {
        "id": str(shift.id),
        "cashier_id": str(shift.cashier_id),
        "cashier_name": shift.cashier.full_name,
        "opened_at": shift.opened_at.isoformat().replace("+00:00", "Z"),
        "closed_at": (
            shift.closed_at.isoformat().replace("+00:00", "Z") if shift.closed_at else None
        ),
        "opening_float_pesewas": int(shift.opening_float_pesewas),
        "declared_cash_pesewas": shift.declared_cash_pesewas,
        "expected_cash_pesewas": shift.expected_cash_pesewas,
        "variance_pesewas": shift.variance_pesewas,
    }


def open_bills() -> list[dict[str, Any]]:
    """Every bill still owing money, newest table activity first — the cashier's work queue."""
    sessions = (
        TableSession.objects.filter(closed_at__isnull=True, settled_at__isnull=True)
        .select_related("table")
        .order_by("opened_at")
    )
    rows: list[dict[str, Any]] = []
    for session in sessions:
        orders = list(Order.objects.filter(session_id=session.id))
        live = [o for o in orders if o.status != OrderStatus.VOIDED]
        paid = int(session.paid_pesewas)
        total = int(session.bill_total_pesewas)
        rows.append(
            {
                "session_id": str(session.id),
                "table_id": str(session.table_id),
                "table_number": session.table.number,
                "opened_at": session.opened_at.isoformat().replace("+00:00", "Z"),
                "order_count": len(live),
                "bill_total_pesewas": total,
                "paid_pesewas": paid,
                "balance_pesewas": total - paid,
                "state": chip_for_session(session.id),
                "payable": all(
                    o.status
                    not in (OrderStatus.SUBMITTED, OrderStatus.PREPARING, OrderStatus.READY)
                    for o in live
                ),
            }
        )
    return rows


def z_report(shift: Shift) -> dict[str, Any]:
    """What the cashier and the owner reconcile at the end of a shift."""
    totals = shift_totals(shift.id, int(shift.opening_float_pesewas))
    payments = (
        Payment.objects.filter(shift_id=shift.id)
        .select_related("session", "session__table")
        .order_by("recorded_at")
    )
    movements = DrawerMovement.objects.filter(shift_id=shift.id).order_by("recorded_at")
    declared = shift.declared_cash_pesewas
    expected = (
        shift.expected_cash_pesewas
        if shift.expected_cash_pesewas is not None
        else totals["expected_cash_pesewas"]
    )
    return {
        **serialize_shift(shift),
        **totals,
        "expected_cash_pesewas": expected,
        "variance_pesewas": (declared - expected) if declared is not None else None,
        "money_taken_pesewas": sum(totals["totals_by_method"].values()),
        "payments": [
            {
                "id": str(p.id),
                "table_number": p.session.table.number,
                "method": p.method,
                "amount_pesewas": int(p.amount_pesewas),
                "external_reference": p.external_reference,
                "recorded_at": p.recorded_at.isoformat().replace("+00:00", "Z"),
                "voided_at": (
                    p.voided_at.isoformat().replace("+00:00", "Z") if p.voided_at else None
                ),
            }
            for p in payments
        ],
        "movements": [
            {
                "id": str(m.id),
                "kind": m.kind,
                "amount_pesewas": int(m.amount_pesewas),
                "reason_code": m.reason_code,
                "note": m.note,
                "recorded_at": m.recorded_at.isoformat().replace("+00:00", "Z"),
            }
            for m in movements
        ],
    }


def current_shift_for(actor_id: uuid.UUID) -> Shift | None:
    return (
        Shift.objects.filter(cashier_id=actor_id, closed_at__isnull=True)
        .select_related("cashier")
        .first()
    )
