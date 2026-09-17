"""
Payments, shifts and the drawer. docs/08-backend-architecture.md §9, ADR-0008.

Every cedi is attached to a shift, the bill is the table session, and settlement happens inside the
same handler as the payment that closes it — so a bill can never be paid in full without being settled.
Money is int pesewas throughout.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import transaction
from django.db.models import Sum

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.money import require_pesewas
from apps.core.roles import MANAGER_ROLES, AggregateType
from apps.core.uuid7 import is_uuid7, uuid7
from apps.floor.models import TableSession
from apps.orders.events import (
    DrawerCounted,
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
from apps.orders.events import (
    DrawerMovement as DrawerMovementPayload,
)
from apps.orders.models import Order, OrderStatus
from apps.payments.models import DrawerMovement, Payment, PaymentMethod, Shift

# An order is still in the kitchen's hands: paying now would close a bill that is still being cooked.
UNSERVED = (OrderStatus.SUBMITTED, OrderStatus.PREPARING, OrderStatus.READY)


def _require_uuid7(value: Any, field: str) -> uuid.UUID:
    if not is_uuid7(value):
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be a client-generated UUIDv7.",
            errors={field: ["Must be UUIDv7."]},
        )
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _require_actor(ctx: CommandContext) -> uuid.UUID:
    if ctx.actor_id is None:
        raise ApiError(403, ErrorCode.ROLE_NOT_ALLOWED, "A staff member must perform this action.")
    return ctx.actor_id


def _require_authorisation(ctx: CommandContext, detail: str) -> None:
    """
    The view layer asks for the manager's PIN via `authorisation_purpose`. This repeats the check at
    the command layer so a new endpoint cannot move money without one by forgetting to declare it.
    """
    if ctx.authorised_by is None:
        raise ApiError(403, ErrorCode.AUTHORISATION_REQUIRED, detail)


def _require_pesewas_field(data: dict[str, Any], field: str, *, allow_zero: bool = False) -> int:
    """
    Money arrives as an integer number of pesewas or not at all. `int()` would quietly turn 75.5
    into 75 and True into 1; require_pesewas rejects both, so a rounding bug cannot reach the drawer.
    """
    try:
        value = require_pesewas(data[field])
    except KeyError as err:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} is required.",
            errors={field: ["Required."]},
        ) from err
    except ValueError as err:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be an integer number of pesewas.",
            errors={field: [str(err)]},
        ) from err
    if not allow_zero and value == 0:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            f"{field} must be greater than zero.",
            errors={field: ["Must be greater than zero."]},
        )
    return value


def open_shift_for(actor_id: uuid.UUID, *, for_update: bool = False) -> Shift | None:
    shifts = Shift.objects.filter(cashier_id=actor_id, closed_at__isnull=True)
    if for_update:
        shifts = shifts.select_for_update()
    return shifts.first()


def require_open_shift(ctx: CommandContext) -> Shift:
    """Every payment and drawer movement belongs to a shift — that is the whole point of the shift."""
    # Locked: the shift row is read to stamp the payment and again to total the drawer at close, so a
    # concurrent close must queue behind this payment rather than count a drawer that is still moving.
    shift = open_shift_for(_require_actor(ctx), for_update=True)
    if shift is None:
        raise ApiError(
            403,
            ErrorCode.SHIFT_REQUIRED,
            "Open a shift with the drawer float before taking money.",
        )
    return shift


def normalise_reference(raw: str | None) -> str | None:
    """MoMo ids are keyed by hand on a phone: trim, strip spaces, upper-case so they match later."""
    if raw is None:
        return None
    cleaned = "".join(raw.split()).upper()
    return cleaned or None


# ------------------------------------------------------------------ shifts


def open_shift(ctx: CommandContext, data: dict[str, Any]) -> CommandOutcome:
    actor_id = _require_actor(ctx)
    shift_id = _require_uuid7(data["id"], "id")
    opening_float = _require_pesewas_field(data, "opening_float_pesewas", allow_zero=True)

    existing = open_shift_for(actor_id)
    if existing is not None:
        raise ApiError(
            409,
            ErrorCode.SHIFT_ALREADY_OPEN,
            "This cashier already has an open shift. Close it before opening another.",
        )
    if Shift.objects.filter(pk=shift_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Shift id already exists.")

    payload = ShiftOpened(
        cashier_id=str(actor_id), opening_float_pesewas=opening_float
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
            "cashier_id": str(actor_id),
            "opening_float_pesewas": opening_float,
            "closed_at": None,
        },
        status=201,
    )


def _assert_can_mutate_shift(ctx: CommandContext, shift: Shift) -> None:
    """
    A drawer belongs to the cashier who opened it. Only that cashier — or a manager standing over the
    till — may count it or move cash out of it, otherwise one cashier's variance lands on another.
    """
    actor_id = _require_actor(ctx)
    if ctx.actor_role in MANAGER_ROLES:
        return
    if actor_id != shift.cashier_id:
        raise ApiError(
            403,
            ErrorCode.ROLE_NOT_ALLOWED,
            "A cashier may only count and move cash on their own shift.",
        )


def _shift_for_write(ctx: CommandContext, shift_id: uuid.UUID) -> Shift:
    try:
        shift = Shift.objects.select_for_update().get(pk=shift_id)
    except Shift.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Shift not found.") from err
    if shift.closed_at is not None:
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Shift is already closed.")
    _assert_can_mutate_shift(ctx, shift)
    return shift


def shift_totals(shift_id: uuid.UUID, opening_float_pesewas: int) -> dict[str, Any]:
    """expected = float + Σ cash − Σ paid out + Σ paid in. Voided payments never count."""
    live = Payment.objects.filter(shift_id=shift_id, voided_at__isnull=True)
    totals_by_method: dict[str, int] = {
        row["method"]: int(row["total"])
        for row in live.values("method").annotate(total=Sum("amount_pesewas"))
    }
    movements = DrawerMovement.objects.filter(shift_id=shift_id)
    paid_out = int(
        movements.filter(kind=DrawerMovement.Kind.PAID_OUT).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    paid_in = int(
        movements.filter(kind=DrawerMovement.Kind.PAID_IN).aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    cash = totals_by_method.get(PaymentMethod.CASH, 0)
    return {
        "opening_float_pesewas": int(opening_float_pesewas),
        "cash_payments_pesewas": cash,
        "paid_out_pesewas": paid_out,
        "paid_in_pesewas": paid_in,
        "expected_cash_pesewas": int(opening_float_pesewas) + cash - paid_out + paid_in,
        "totals_by_method": totals_by_method,
        "payment_count": live.count(),
    }


def close_shift(ctx: CommandContext, shift_id: uuid.UUID, data: dict[str, Any]) -> CommandOutcome:
    shift = _shift_for_write(ctx, shift_id)
    declared = _require_pesewas_field(data, "declared_cash_pesewas", allow_zero=True)
    note = data.get("note") or ""

    totals = shift_totals(shift.id, int(shift.opening_float_pesewas))
    expected = totals["expected_cash_pesewas"]
    variance = declared - expected

    counted = DrawerCounted(
        declared_cash_pesewas=declared,
        expected_cash_pesewas=expected,
        variance_pesewas=variance,
    ).to_payload()
    closed = ShiftClosed(
        cashier_id=str(shift.cashier_id),
        opening_float_pesewas=totals["opening_float_pesewas"],
        cash_payments_pesewas=totals["cash_payments_pesewas"],
        paid_out_pesewas=totals["paid_out_pesewas"],
        paid_in_pesewas=totals["paid_in_pesewas"],
        expected_cash_pesewas=expected,
        declared_cash_pesewas=declared,
        variance_pesewas=variance,
        totals_by_method=totals["totals_by_method"],
        note=note,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(AggregateType.SHIFT, shift.id, EventType.DRAWER_COUNTED, counted),
            EventDraft(AggregateType.SHIFT, shift.id, EventType.SHIFT_CLOSED, closed),
        ],
        response={
            "id": str(shift.id),
            "cashier_id": str(shift.cashier_id),
            **totals,
            "declared_cash_pesewas": declared,
            "variance_pesewas": variance,
            "note": note,
        },
    )


def record_drawer_movement(
    ctx: CommandContext, shift_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    _require_authorisation(ctx, "Moving cash in or out of the drawer needs manager authorisation.")
    shift = _shift_for_write(ctx, shift_id)
    kind = data["kind"]
    if kind not in DrawerMovement.Kind.values:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "kind must be NO_SALE, PAID_OUT or PAID_IN.",
            errors={"kind": ["Invalid."]},
        )
    # A no-sale is the drawer opening with no money moving. It still leaves a trace.
    if kind == DrawerMovement.Kind.NO_SALE:
        amount = 0
    else:
        amount = _require_pesewas_field(data, "amount_pesewas")

    movement_id = uuid7()
    payload = DrawerMovementPayload(
        movement_id=str(movement_id),
        kind=str(kind),
        amount_pesewas=amount,
        note=data.get("note") or "",
    ).to_payload()
    return CommandOutcome(
        events=[EventDraft(AggregateType.SHIFT, shift.id, EventType.DRAWER_MOVEMENT, payload)],
        response={
            "id": str(movement_id),
            "shift_id": str(shift.id),
            "kind": str(kind),
            "amount_pesewas": amount,
        },
        status=201,
    )


# ------------------------------------------------------------------ payments


def _session_for_write(session_id: uuid.UUID) -> TableSession:
    try:
        session = (
            TableSession.objects.select_for_update().select_related("table").get(pk=session_id)
        )
    except TableSession.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err
    return session


def _live_paid(session_id: uuid.UUID) -> int:
    return int(
        Payment.objects.filter(session_id=session_id, voided_at__isnull=True).aggregate(
            s=Sum("amount_pesewas")
        )["s"]
        or 0
    )


def _settlement_events(
    session: TableSession,
    paid: int,
    payments_summary: list[dict[str, Any]],
    served: list[Order],
):
    """SESSION_SETTLED plus one ORDER_CLOSED per served order — the bill is done."""
    events = [
        EventDraft(
            AggregateType.SESSION,
            session.id,
            EventType.SESSION_SETTLED,
            SessionSettled(
                table_number=session.table.number,
                bill_total_pesewas=int(session.bill_total_pesewas),
                paid_pesewas=paid,
                order_ids=[str(o.id) for o in served],
                payments=payments_summary,
            ).to_payload(),
        )
    ]
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
    return events


def record_payment(
    ctx: CommandContext, session_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    shift = require_open_shift(ctx)
    session = _session_for_write(session_id)
    if session.closed_at is not None:
        raise ApiError(409, ErrorCode.SESSION_CLOSED, "This bill is closed.")

    # Locked before the bill is priced: a round cannot reach the kitchen, or be served, between the
    # unserved check here and the settlement events built at the end of this handler.
    orders = list(
        Order.objects.select_for_update().filter(session_id=session.id).order_by("order_number")
    )
    unserved = [o for o in orders if o.status in UNSERVED]
    if unserved:
        numbers = ", ".join(f"#{o.order_number}" for o in unserved if o.order_number)
        raise ApiError(
            409,
            ErrorCode.UNSERVED_ORDERS,
            f"Serve every order before taking payment: {numbers or 'order still in the kitchen'}.",
        )

    payment_id = _require_uuid7(data["id"], "id")
    if Payment.objects.filter(pk=payment_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Payment id already exists.")

    amount = _require_pesewas_field(data, "amount_pesewas")
    method = data["method"]
    if method not in PaymentMethod.values:
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "Unknown payment method.",
            errors={"method": ["Invalid."]},
        )
    bill_total = int(session.bill_total_pesewas)
    already_paid = _live_paid(session.id)
    balance_before = bill_total - already_paid

    if amount > balance_before:
        raise ApiError(
            422,
            ErrorCode.OVERPAYMENT,
            f"This bill only has {balance_before} pesewas left to pay.",
            errors={"balance_pesewas": [balance_before]},
        )

    tendered: int | None = data.get("tendered_pesewas")
    change: int | None = None
    if method == PaymentMethod.CASH:
        # An untendered cash payment is the exact amount: the cashier took the note and gave no change.
        if tendered is None:
            tendered = amount
        else:
            tendered = _require_pesewas_field(data, "tendered_pesewas", allow_zero=True)
        if tendered < amount:
            raise ApiError(
                422,
                ErrorCode.TENDERED_INSUFFICIENT,
                "The cash handed over is less than the amount being paid.",
                errors={"tendered_pesewas": [tendered], "amount_pesewas": [amount]},
            )
        change = tendered - amount
    else:
        tendered = None

    reference = normalise_reference(data.get("external_reference"))
    order_id = data.get("order_id")
    if order_id is not None and not any(o.id == order_id for o in orders):
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order not found on this bill.")

    paid_after = already_paid + amount
    balance_after = bill_total - paid_after

    payload = PaymentRecorded(
        payment_id=str(payment_id),
        shift_id=str(shift.id),
        method=str(method),
        amount_pesewas=amount,
        tendered_pesewas=tendered,
        change_pesewas=change,
        external_reference=reference,
        order_id=str(order_id) if order_id else None,
        bill_total_pesewas=bill_total,
        paid_pesewas=paid_after,
        balance_pesewas=balance_after,
    ).to_payload()

    events = [EventDraft(AggregateType.SESSION, session.id, EventType.PAYMENT_RECORDED, payload)]
    settled = balance_after == 0
    if settled:
        summary = [
            {"method": p.method, "amount_pesewas": int(p.amount_pesewas)}
            for p in Payment.objects.filter(session_id=session.id, voided_at__isnull=True)
        ]
        summary.append({"method": str(method), "amount_pesewas": amount})
        served = [o for o in orders if o.status == OrderStatus.SERVED]
        events += _settlement_events(session, paid_after, summary, served)

    return CommandOutcome(
        events=events,
        response={
            "id": str(payment_id),
            "session_id": str(session.id),
            "shift_id": str(shift.id),
            "method": str(method),
            "amount_pesewas": amount,
            "tendered_pesewas": tendered,
            "change_pesewas": change,
            "external_reference": reference,
            "bill_total_pesewas": bill_total,
            "paid_pesewas": paid_after,
            "balance_pesewas": balance_after,
            "settled": settled,
        },
        status=201,
    )


def _reopen_events(session: TableSession, note: str):
    """Undo a settlement: the bill is live again and its closed orders go back to SERVED."""
    closed = list(
        Order.objects.select_for_update()
        .filter(session_id=session.id, status=OrderStatus.CLOSED)
        .order_by("order_number")
    )
    events = [
        EventDraft(
            AggregateType.SESSION,
            session.id,
            EventType.SESSION_REOPENED,
            SessionReopened(
                table_number=session.table.number,
                order_ids=[str(o.id) for o in closed],
                note=note,
            ).to_payload(),
        )
    ]
    for order in closed:
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
            )
        )
    return events


def _alert_owner_after_commit(ctx: CommandContext, session: TableSession, note: str) -> None:
    """
    The owner hears about a reopened bill without having to go looking for it. Queued on commit so a
    slow mail server cannot hold the till open, and so a rolled-back reopen sends nothing.
    """
    from apps.accounts.models import Staff
    from apps.payments.tasks import notify_owner_reopen

    wanted = [i for i in (ctx.actor_id, ctx.authorised_by) if i is not None]
    names = {s.id: s.full_name for s in Staff.objects.filter(id__in=wanted)}
    payload = (
        str(ctx.restaurant_id),
        str(session.id),
        session.table.number,
        names.get(ctx.actor_id, "A staff member") if ctx.actor_id else "A staff member",
        names.get(ctx.authorised_by, "a manager") if ctx.authorised_by else "a manager",
        note,
    )
    transaction.on_commit(lambda: notify_owner_reopen.delay(*payload))


def void_payment(
    ctx: CommandContext, payment_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    _require_authorisation(ctx, "Voiding a payment needs manager authorisation.")
    try:
        payment = Payment.objects.select_for_update().get(pk=payment_id)
    except Payment.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Payment not found.") from err
    if payment.voided_at is not None:
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Payment is already voided.")

    session = _session_for_write(payment.session_id)
    note = data.get("note") or ""
    amount = int(payment.amount_pesewas)
    paid_after = _live_paid(session.id) - amount
    balance_after = int(session.bill_total_pesewas) - paid_after

    events = [
        EventDraft(
            AggregateType.SESSION,
            session.id,
            EventType.PAYMENT_VOIDED,
            PaymentVoided(
                payment_id=str(payment.id),
                amount_pesewas=amount,
                method=payment.method,
                balance_pesewas=balance_after,
                note=note,
            ).to_payload(),
        )
    ]
    # Voiding money off a settled bill puts the bill back in play; the owner is told (flagged events).
    reopened = session.settled_at is not None and balance_after > 0
    if reopened:
        reason = note or "payment voided"
        events += _reopen_events(session, reason)
        _alert_owner_after_commit(ctx, session, reason)

    return CommandOutcome(
        events=events,
        response={
            "id": str(payment.id),
            "session_id": str(session.id),
            "voided": True,
            "amount_pesewas": amount,
            "paid_pesewas": paid_after,
            "balance_pesewas": balance_after,
            "session_reopened": reopened,
        },
    )


def reopen_session(
    ctx: CommandContext, session_id: uuid.UUID, data: dict[str, Any]
) -> CommandOutcome:
    _require_authorisation(ctx, "Reopening a bill needs manager authorisation.")
    session = _session_for_write(session_id)
    if session.settled_at is None and session.closed_at is None:
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "This bill is already open.")

    note = data.get("note") or ""
    events = _reopen_events(session, note)
    _alert_owner_after_commit(ctx, session, note)
    return CommandOutcome(
        events=events,
        response={
            "id": str(session.id),
            "reopened": True,
            "table_number": session.table.number,
            "bill_total_pesewas": int(session.bill_total_pesewas),
            "paid_pesewas": _live_paid(session.id),
            "balance_pesewas": int(session.bill_total_pesewas) - _live_paid(session.id),
        },
    )
