"""Pesewas helpers owned by payments. Integers only."""

from __future__ import annotations

from django.db.models import Q, Sum

from apps.payments.models import DrawerMovement, Payment, PaymentMethod, Shift


def normalize_external_reference(raw: str | None) -> str | None:
    """Trim, uppercase, strip internal spaces — tired cashiers type MoMo refs."""
    if raw is None:
        return None
    cleaned = "".join(raw.strip().upper().split())
    return cleaned or None


def cash_payments_total(shift_id) -> int:
    total = (
        Payment.objects.filter(
            shift_id=shift_id, method=PaymentMethod.CASH, voided_at__isnull=True
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    return int(total)


def movement_totals(shift_id) -> tuple[int, int]:
    """Return (paid_out, paid_in) for non-voided movements (all movements are kept)."""
    paid_out = (
        DrawerMovement.objects.filter(
            shift_id=shift_id, kind=DrawerMovement.Kind.PAID_OUT
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    paid_in = (
        DrawerMovement.objects.filter(
            shift_id=shift_id, kind=DrawerMovement.Kind.PAID_IN
        ).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    return int(paid_out), int(paid_in)


def expected_cash_pesewas(shift: Shift) -> int:
    """float + Σ CASH payments − Σ PAID_OUT + Σ PAID_IN (non-voided payments only)."""
    cash = cash_payments_total(shift.id)
    paid_out, paid_in = movement_totals(shift.id)
    return int(shift.opening_float_pesewas) + cash - paid_out + paid_in


def totals_by_method(shift_id) -> dict[str, int]:
    rows = (
        Payment.objects.filter(shift_id=shift_id, voided_at__isnull=True)
        .values("method")
        .annotate(total=Sum("amount_pesewas"))
    )
    return {row["method"]: int(row["total"] or 0) for row in rows}


def session_paid_pesewas(session_id) -> int:
    total = (
        Payment.objects.filter(session_id=session_id, voided_at__isnull=True).aggregate(
            s=Sum("amount_pesewas")
        )["s"]
        or 0
    )
    return int(total)


def open_shift_for(actor_id) -> Shift | None:
    if actor_id is None:
        return None
    return (
        Shift.objects.select_for_update()
        .filter(cashier_id=actor_id, closed_at__isnull=True)
        .first()
    )
