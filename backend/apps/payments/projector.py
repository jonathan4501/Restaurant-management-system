"""
SHIFT_* and payment projections. Deterministic: every value comes from the event or from rows an
earlier event already wrote. Never reads the clock — `event.created_at` is the time of record.
"""

from __future__ import annotations

import uuid

from django.db.models import Sum

from apps.core.projections import project
from apps.floor.models import TableSession
from apps.orders.events import EventType
from apps.orders.models import OrderEvent
from apps.payments.models import DrawerMovement, Payment, Shift


def _refresh_session_paid(restaurant_id: uuid.UUID, session_id: uuid.UUID) -> None:
    paid = (
        Payment.objects.unscoped()
        .filter(restaurant_id=restaurant_id, session_id=session_id, voided_at__isnull=True)
        .aggregate(s=Sum("amount_pesewas"))["s"]
        or 0
    )
    TableSession.objects.unscoped().filter(restaurant_id=restaurant_id, id=session_id).update(
        paid_pesewas=int(paid)
    )


@project(EventType.SHIFT_OPENED)
def shift_opened(event: OrderEvent) -> None:
    payload = event.payload
    if "cashier_id" not in payload:
        return
    Shift.objects.update_or_create(
        id=event.aggregate_id,
        defaults={
            "restaurant_id": event.restaurant_id,
            "cashier_id": uuid.UUID(payload["cashier_id"]),
            "opened_at": event.created_at,
            "closed_at": None,
            "opening_float_pesewas": int(payload["opening_float_pesewas"]),
            "declared_cash_pesewas": None,
            "expected_cash_pesewas": None,
            "closed_by_id": None,
            "notes": "",
        },
    )


@project(EventType.DRAWER_MOVEMENT)
def drawer_movement(event: OrderEvent) -> None:
    payload = event.payload
    if event.actor_id is None or event.authorised_by_id is None or "movement_id" not in payload:
        return  # Both names are required by the model; the command always supplies them.
    DrawerMovement.objects.update_or_create(
        id=uuid.UUID(payload["movement_id"]),
        defaults={
            "restaurant_id": event.restaurant_id,
            "shift_id": event.aggregate_id,
            "kind": payload["kind"],
            "amount_pesewas": int(payload["amount_pesewas"]),
            "reason_code": event.reason_code or "",
            "note": payload.get("note") or "",
            "recorded_by_id": event.actor_id,
            "authorised_by_id": event.authorised_by_id,
            "recorded_at": event.created_at,
        },
    )


@project(EventType.DRAWER_COUNTED)
def drawer_counted(event: OrderEvent) -> None:
    payload = event.payload
    if "declared_cash_pesewas" not in payload:
        return
    Shift.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(
        declared_cash_pesewas=int(payload["declared_cash_pesewas"]),
        expected_cash_pesewas=int(payload["expected_cash_pesewas"]),
    )


@project(EventType.SHIFT_CLOSED)
def shift_closed(event: OrderEvent) -> None:
    Shift.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(
        closed_at=event.created_at,
        closed_by_id=event.actor_id,
        notes=event.payload.get("note") or "",
    )


@project(EventType.PAYMENT_RECORDED)
def payment_recorded(event: OrderEvent) -> None:
    payload = event.payload
    # A projector must never break a rebuild: skip anything that is not a real payment event
    # (runner unit tests append stub payloads). record_payment always sends the full shape.
    if event.actor_id is None or "payment_id" not in payload or "shift_id" not in payload:
        return
    order_id = payload.get("order_id")
    Payment.objects.update_or_create(
        id=uuid.UUID(payload["payment_id"]),
        defaults={
            "restaurant_id": event.restaurant_id,
            "session_id": event.aggregate_id,
            "order_id": uuid.UUID(order_id) if order_id else None,
            "shift_id": uuid.UUID(payload["shift_id"]),
            "method": payload["method"],
            "amount_pesewas": int(payload["amount_pesewas"]),
            "tendered_pesewas": payload.get("tendered_pesewas"),
            "change_pesewas": payload.get("change_pesewas"),
            "external_reference": payload.get("external_reference"),
            "recorded_by_id": event.actor_id,
            "recorded_at": event.created_at,
            "voided_at": None,
            "void_reason": None,
            "voided_by_id": None,
            "void_authorised_by_id": None,
        },
    )
    _refresh_session_paid(event.restaurant_id, event.aggregate_id)


@project(EventType.PAYMENT_VOIDED)
def payment_voided(event: OrderEvent) -> None:
    payload = event.payload
    if "payment_id" not in payload:
        return
    Payment.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=uuid.UUID(payload["payment_id"])
    ).update(
        voided_at=event.created_at,
        void_reason=event.reason_code,
        voided_by_id=event.actor_id,
        void_authorised_by_id=event.authorised_by_id,
    )
    _refresh_session_paid(event.restaurant_id, event.aggregate_id)
