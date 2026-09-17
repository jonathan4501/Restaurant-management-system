"""Shift, drawer, payment and session-settlement command handlers (WS05)."""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.db.models import Sum

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.money import require_pesewas
from apps.core.roles import AggregateType, ActorRole, MANAGER_ROLES
from apps.core.uuid7 import is_uuid7
from apps.floor.models import TableSession
from apps.orders.events import (
    DrawerCounted,
    DrawerMovement as DrawerMovementPayload,
    EventType,
    OrderClosed,
    OrderReopened,
    PaymentRecorded,
    PaymentVoided,
    SessionReopened,
    SessionSettled,
    ShiftClosed,
    ShiftOpened,
)
from apps.orders.models import Order, OrderStatus
from apps.payments.models import DrawerMovement, Payment, PaymentMethod, Shift
from apps.payments.tasks import notify_owner_reopen

UNSERVED = frozenset(
    {OrderStatus.SUBMITTED, OrderStatus.PREPARING, OrderStatus.READY}
)
CASHIER_ROLES = frozenset({ActorRole.CASHIER, ActorRole.MANAGER, ActorRole.OWNER})


def _require_uuid7(value: uuid.UUID, field: str = "id") -> uuid.UUID:
    if not is_uuid7(value):
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a client-generated UUIDv7.",
            errors={field: ["Must be UUIDv7."]},
        )
    return value


def _require_pesewas_field(data: dict[str, Any], field: str, *, allow_zero: bool = False) -> int:
    try:
        value = require_pesewas(data[field])
    except (KeyError, ValueError) as err:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            str(err) if not isinstance(err, KeyError) else f"{field} is required.",
            errors={field: [str(err)]},
        ) from err
    if not allow_zero and value == 0:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be greater than zero.",
            errors={field: ["Must be > 0."]},
        )
    return value


def normalise_external_reference(raw: str | None) -> str | None:
    """Trim, upper-case, strip spaces — tired cashiers type MoMo ids."""
    if raw is None:
        return None
    cleaned = "".join(raw.strip().upper().split())
    return cleaned or None


def require_open_shift(ctx: CommandContext) -> Shift:
    if ctx.actor_id is None:
        raise ApiError(403, ErrorCode.SHIFT_REQUIRED, "An open shift is required.")
    try:
        return Shift.objects.select_for_update().get(
            cashier_id=ctx.actor_id, closed_at__isnull=True
        )
    except Shift.DoesNotExist as err:
        raise ApiError(
            403, ErrorCode.SHIFT_REQUIRED, "Open a shift before recording payments."
        ) from err


def _lock_session(session_id: uuid.UUID) -> TableSession:
    try:
        return (
            TableSession.objects.select_for_update()
            .select_related("table")
            .get(pk=session_id)
        )
    except TableSession.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err


def _lock_shift(shift_id: uuid.UUID) -> Shift:
    try:
        return Shift.objects.select_for_update().get(pk=shift_id)
    except Shift.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Shift not found.") from err


def _assert_can_mutate_shift(ctx: CommandContext, shift: Shift) -> None:
    if ctx.actor_role in MANAGER_ROLES:
        return
    if ctx.actor_id != shift.cashier_id:
        raise ApiError(403, ErrorCode.ROLE_NOT_ALLOWED, "Cashiers may only manage their own shift.")


def expected_cash_pesewas(shift: Shift) -> int:
    """float + Σ non-voided CASH payments − Σ PAID_OUT + Σ PAID_IN."""
    cash = (
        Payment.objects.filter(shift_id=shift.id, method=PaymentMethod.CASH, voided_at__isnull=True)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    paid_out = (
        DrawerMovement.objects.filter(shift_id=shift.id, kind=DrawerMovement.Kind.PAID_OUT)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    paid_in = (
        DrawerMovement.objects.filter(shift_id=shift.id, kind=DrawerMovement.Kind.PAID_IN)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    return int(shift.opening_float_pesewas) + int(cash) - int(paid_out) + int(paid_in)


def totals_by_method(shift: Shift) -> dict[str, int]:
    rows = (
        Payment.objects.filter(shift_id=shift.id, voided_at__isnull=True)
        .values("method")
        .annotate(total=Sum("amount_pesewas"))
    )
    return {r["method"]: int(r["total"]) for r in rows}


def _payment_summary(payment: Payment) -> dict[str, Any]:
    return {
        "id": str(payment.id),
        "method": payment.method,
        "amount_pesewas": int(payment.amount_pesewas),
    }


def open_shift(ctx: CommandContext, data: dict[str, Any]) -> CommandOutcome:
    shift_id = _require_uuid7(data["id"])
    opening_float = _require_pesewas_field(data, "opening_float_pesewas", allow_zero=True)

    if ctx.actor_id is None:
        raise ApiError(403, ErrorCode.ROLE_NOT_ALLOWED, "A staff member must open the shift.")

    if Shift.objects.filter(cashier_id=ctx.actor_id, closed_at__isnull=True).exists():
        raise ApiError(409, ErrorCode.SHIFT_ALREADY_OPEN, "You already have an open shift.")

    if Shift.objects.filter(pk=shift_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Shift id already exists.")

    payload = ShiftOpened(
        cashier_id=str(ctx.actor_id),
        opening_float_pesewas=opening_float,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.SHIFT,
                shift_id,
                EventType.SHIFT_OPENED,
                payload,
                event_id=shift_id,
            )
        ],
        response={
            "id": str(shift_id),
            "cashier_id": str(ctx.actor_id),
            "opening_float_pesewas": opening_float,
            "closed_at": None,
        },
        status=201,
    )


def record_drawer_movement(
    ctx: CommandContext, shift_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    if ctx.authorised_by is None:
        raise ApiError(
            403,
            ErrorCode.AUTHORISATION_REQUIRED,
            "Drawer movements need manager authorisation.",
        )

    shift = _lock_shift(shift_id)
    if shift.closed_at is not None:
        raise ApiError(409, ErrorCode.ILLEGAL_TRANSITION, "Cannot move cash on a closed shift.")
    _assert_can_mutate_shift(ctx, shift)

    movement_id = _require_uuid7(data["id"])
    kind = data["kind"]
    if kind not in DrawerMovement.Kind.values:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "kind must be NO_SALE, PAID_OUT or PAID_IN.",
            errors={"kind": ["Invalid."]},
        )

    if kind == DrawerMovement.Kind.NO_SALE:
        amount = 0
    else:
        amount = _require_pesewas_field(data, "amount_pesewas")

    note = data.get("note") or ""
    reason = ctx.reason_code or data.get("reason_code")
    if not reason:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "reason_code is required.",
            errors={"reason_code": ["Required."]},
        )

    if DrawerMovement.objects.filter(pk=movement_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Movement id already exists.")

    payload = DrawerMovementPayload(
        movement_id=str(movement_id),
        kind=kind,
        amount_pesewas=amount,
        note=note,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.SHIFT,
                shift.id,
                EventType.DRAWER_MOVEMENT,
                payload,
                event_id=movement_id,
                reason_code=reason,
            )
        ],
        response={
            "id": str(movement_id),
            "shift_id": str(shift.id),
            "kind": kind,
            "amount_pesewas": amount,
            "reason_code": reason,
            "note": note,
        },
        status=201,
    )


def close_shift(ctx: CommandContext, shift_id: uuid.UUID, data: dict[str, Any]) -> CommandOutcome:
    shift = _lock_shift(shift_id)
    if shift.closed_at is not None:
        raise ApiError(409, ErrorCode.ILLEGAL_TRANSITION, "Shift is already closed.")
    _assert_can_mutate_shift(ctx, shift)

    declared = _require_pesewas_field(data, "declared_cash_pesewas", allow_zero=True)
    notes = data.get("notes") or ""
    expected = expected_cash_pesewas(shift)
    variance = declared - expected

    cash_payments = (
        Payment.objects.filter(shift_id=shift.id, method=PaymentMethod.CASH, voided_at__isnull=True)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    paid_out = (
        DrawerMovement.objects.filter(shift_id=shift.id, kind=DrawerMovement.Kind.PAID_OUT)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    paid_in = (
        DrawerMovement.objects.filter(shift_id=shift.id, kind=DrawerMovement.Kind.PAID_IN)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    by_method = totals_by_method(shift)

    counted = DrawerCounted(
        declared_cash_pesewas=declared,
        expected_cash_pesewas=expected,
        variance_pesewas=variance,
    ).to_payload()
    closed = ShiftClosed(
        cashier_id=str(shift.cashier_id),
        opening_float_pesewas=int(shift.opening_float_pesewas),
        cash_payments_pesewas=int(cash_payments),
        paid_out_pesewas=int(paid_out),
        paid_in_pesewas=int(paid_in),
        expected_cash_pesewas=expected,
        declared_cash_pesewas=declared,
        variance_pesewas=variance,
        totals_by_method=by_method,
        note=notes,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(AggregateType.SHIFT, shift.id, EventType.DRAWER_COUNTED, counted),
            EventDraft(AggregateType.SHIFT, shift.id, EventType.SHIFT_CLOSED, closed),
        ],
        response={
            "id": str(shift.id),
            "opening_float_pesewas": int(shift.opening_float_pesewas),
            "expected_cash_pesewas": expected,
            "declared_cash_pesewas": declared,
            "variance_pesewas": variance,
            "totals_by_method": by_method,
            "notes": notes,
        },
    )


def record_payment(
    ctx: CommandContext, session_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    shift = require_open_shift(ctx)
    session = _lock_session(session_id)

    if session.closed_at is not None:
        raise ApiError(409, ErrorCode.SESSION_CLOSED, "Session is closed.")
    if session.settled_at is not None:
        raise ApiError(
            409, ErrorCode.ILLEGAL_TRANSITION, "Session is settled; reopen before taking payment."
        )

    payment_id = _require_uuid7(data["id"])
    method = data["method"]
    if method not in PaymentMethod.values:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "Invalid payment method.",
            errors={"method": ["Invalid."]},
        )

    amount = _require_pesewas_field(data, "amount_pesewas")
    order_id = data.get("order_id")
    external_reference = normalise_external_reference(data.get("external_reference"))

    orders = list(Order.objects.select_for_update().filter(session_id=session.id))
    if any(o.status in UNSERVED for o in orders):
        raise ApiError(
            409,
            ErrorCode.UNSERVED_ORDERS,
            "Cannot take payment while food is still in the kitchen.",
        )

    bill_total = int(session.bill_total_pesewas)
    paid = int(session.paid_pesewas)
    balance = bill_total - paid
    if amount > balance:
        raise ApiError(
            422,
            ErrorCode.OVERPAYMENT,
            f"Payment of {amount} exceeds balance {balance}.",
        )

    tendered: int | None = None
    change: int | None = None
    if method == PaymentMethod.CASH:
        if "tendered_pesewas" not in data or data["tendered_pesewas"] is None:
            raise ApiError(
                400,
                ErrorCode.VALIDATION_ERROR,
                "tendered_pesewas is required for cash.",
                errors={"tendered_pesewas": ["Required for CASH."]},
            )
        tendered = _require_pesewas_field(data, "tendered_pesewas", allow_zero=True)
        if tendered < amount:
            raise ApiError(
                422,
                ErrorCode.TENDERED_INSUFFICIENT,
                "Cash tendered must cover the payment amount.",
            )
        change = tendered - amount

    if Payment.objects.filter(pk=payment_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Payment id already exists.")

    new_paid = paid + amount
    new_balance = bill_total - new_paid

    events: list[EventDraft] = [
        EventDraft(
            AggregateType.SESSION,
            session.id,
            EventType.PAYMENT_RECORDED,
            PaymentRecorded(
                payment_id=str(payment_id),
                shift_id=str(shift.id),
                method=method,
                amount_pesewas=amount,
                tendered_pesewas=tendered,
                change_pesewas=change,
                external_reference=external_reference,
                order_id=str(order_id) if order_id else None,
                bill_total_pesewas=bill_total,
                paid_pesewas=new_paid,
                balance_pesewas=new_balance,
            ).to_payload(),
            event_id=payment_id,
            order_id=order_id,
        )
    ]

    response: dict[str, Any] = {
        "id": str(payment_id),
        "session_id": str(session.id),
        "shift_id": str(shift.id),
        "method": method,
        "amount_pesewas": amount,
        "tendered_pesewas": tendered,
        "change_pesewas": change,
        "external_reference": external_reference,
        "bill_total_pesewas": bill_total,
        "paid_pesewas": new_paid,
        "balance_pesewas": new_balance,
        "settled": False,
    }

    if new_balance == 0:
        served = [o for o in orders if o.status == OrderStatus.SERVED]
        order_ids = [str(o.id) for o in served]
        # Existing non-voided payments plus this one (not yet projected).
        payment_rows = [
            _payment_summary(p)
            for p in Payment.objects.filter(session_id=session.id, voided_at__isnull=True)
        ]
        payment_rows.append(
            {"id": str(payment_id), "method": method, "amount_pesewas": amount}
        )
        events.append(
            EventDraft(
                AggregateType.SESSION,
                session.id,
                EventType.SESSION_SETTLED,
                SessionSettled(
                    table_number=session.table.number,
                    bill_total_pesewas=bill_total,
                    paid_pesewas=new_paid,
                    order_ids=order_ids,
                    payments=payment_rows,
                ).to_payload(),
            )
        )
        for order in served:
            events.append(
                EventDraft(
                    AggregateType.ORDER,
                    order.id,
                    EventType.ORDER_CLOSED,
                    OrderClosed(
                        order_number=int(order.order_number or 0),
                        session_id=str(session.id),
                        total_pesewas=int(order.total_pesewas),
                    ).to_payload(),
                    order_id=order.id,
                )
            )
        response["settled"] = True
        response["closed_order_ids"] = order_ids

    return CommandOutcome(events=events, response=response, status=201)


def void_payment(ctx: CommandContext, payment_id: uuid.UUID, data: dict[str, Any]) -> CommandOutcome:
    if ctx.authorised_by is None:
        raise ApiError(
            403,
            ErrorCode.AUTHORISATION_REQUIRED,
            "Voiding a payment needs manager authorisation.",
        )

    reason = ctx.reason_code or data.get("reason_code")
    if not reason:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "reason_code is required.",
            errors={"reason_code": ["Required."]},
        )

    try:
        payment = Payment.objects.select_for_update().get(pk=payment_id)
    except Payment.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Payment not found.") from err

    if payment.voided_at is not None:
        raise ApiError(409, ErrorCode.ILLEGAL_TRANSITION, "Payment is already voided.")

    session = _lock_session(payment.session_id)
    was_settled = session.settled_at is not None
    bill_total = int(session.bill_total_pesewas)
    new_paid = int(session.paid_pesewas) - int(payment.amount_pesewas)
    new_balance = bill_total - new_paid
    note = data.get("note") or ""

    events: list[EventDraft] = [
        EventDraft(
            AggregateType.SESSION,
            session.id,
            EventType.PAYMENT_VOIDED,
            PaymentVoided(
                payment_id=str(payment.id),
                amount_pesewas=int(payment.amount_pesewas),
                method=payment.method,
                balance_pesewas=new_balance,
                note=note,
            ).to_payload(),
            reason_code=reason,
        )
    ]

    closed_orders: list[Order] = []
    if was_settled:
        closed_orders = list(
            Order.objects.select_for_update().filter(
                session_id=session.id, status=OrderStatus.CLOSED
            )
        )
        order_ids = [str(o.id) for o in closed_orders]
        events.append(
            EventDraft(
                AggregateType.SESSION,
                session.id,
                EventType.SESSION_REOPENED,
                SessionReopened(
                    table_number=session.table.number,
                    order_ids=order_ids,
                    note=note,
                ).to_payload(),
                reason_code=reason,
            )
        )
        for order in closed_orders:
            events.append(
                EventDraft(
                    AggregateType.ORDER,
                    order.id,
                    EventType.ORDER_REOPENED,
                    OrderReopened(
                        order_number=int(order.order_number or 0),
                        session_id=str(session.id),
                        note=note,
                    ).to_payload(),
                    order_id=order.id,
                    reason_code=reason,
                )
            )

        restaurant_id = str(ctx.restaurant_id)
        sid = str(session.id)

        def _notify() -> None:
            notify_owner_reopen.delay(restaurant_id, sid, reason)

        transaction.on_commit(_notify)

    return CommandOutcome(
        events=events,
        response={
            "id": str(payment.id),
            "voided": True,
            "session_id": str(session.id),
            "balance_pesewas": new_balance,
            "paid_pesewas": new_paid,
            "session_reopened": was_settled,
            "reopened_order_ids": [str(o.id) for o in closed_orders],
            "reason_code": reason,
        },
    )


def reopen_session(
    ctx: CommandContext, session_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    if ctx.authorised_by is None:
        raise ApiError(
            403,
            ErrorCode.AUTHORISATION_REQUIRED,
            "Reopening a bill needs manager authorisation.",
        )

    reason = ctx.reason_code or data.get("reason_code")
    if not reason:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "reason_code is required.",
            errors={"reason_code": ["Required."]},
        )

    session = _lock_session(session_id)
    if session.settled_at is None and session.closed_at is None:
        raise ApiError(
            409, ErrorCode.ILLEGAL_TRANSITION, "Session is not settled or closed."
        )

    note = data.get("note") or ""
    closed_orders = list(
        Order.objects.select_for_update().filter(
            session_id=session.id, status=OrderStatus.CLOSED
        )
    )
    order_ids = [str(o.id) for o in closed_orders]

    events: list[EventDraft] = [
        EventDraft(
            AggregateType.SESSION,
            session.id,
            EventType.SESSION_REOPENED,
            SessionReopened(
                table_number=session.table.number,
                order_ids=order_ids,
                note=note,
            ).to_payload(),
            reason_code=reason,
        )
    ]
    for order in closed_orders:
        events.append(
            EventDraft(
                AggregateType.ORDER,
                order.id,
                EventType.ORDER_REOPENED,
                OrderReopened(
                    order_number=int(order.order_number or 0),
                    session_id=str(session.id),
                    note=note,
                ).to_payload(),
                order_id=order.id,
                reason_code=reason,
            )
        )

    restaurant_id = str(ctx.restaurant_id)
    sid = str(session.id)

    def _notify() -> None:
        notify_owner_reopen.delay(restaurant_id, sid, reason)

    transaction.on_commit(_notify)

    return CommandOutcome(
        events=events,
        response={
            "id": str(session.id),
            "reopened": True,
            "order_ids": order_ids,
            "reason_code": reason,
        },
    )
