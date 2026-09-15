"""Floor / session command handlers."""

from __future__ import annotations

import uuid
from typing import Any

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.roles import AggregateType
from apps.core.uuid7 import is_uuid7
from apps.floor.models import Table, TableSession
from apps.orders.events import EventType, SessionClosed, SessionOpened
from apps.orders.models import Order, OrderStatus


def open_session(ctx: CommandContext, data: dict[str, Any]) -> CommandOutcome:
    session_id = data["id"]
    if not is_uuid7(session_id):
        raise ApiError(
            400,
            ErrorCode.VALIDATION_ERROR,
            "id must be a client-generated UUIDv7.",
            errors={"id": ["Must be UUIDv7."]},
        )
    table_id = data["table_id"]
    party_size = data.get("party_size")

    try:
        table = Table.objects.select_for_update().get(pk=table_id, is_active=True)
    except Table.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Table not found.") from err

    if TableSession.objects.filter(table_id=table.id, closed_at__isnull=True).exists():
        raise ApiError(
            409, ErrorCode.TABLE_OCCUPIED, f"Table {table.number} already has an open session."
        )

    if TableSession.objects.filter(pk=session_id).exists():
        raise ApiError(409, ErrorCode.VALIDATION_ERROR, "Session id already exists.")

    if ctx.actor_id is None:
        raise ApiError(403, ErrorCode.ROLE_NOT_ALLOWED, "A staff member must open the session.")

    payload = SessionOpened(
        table_id=str(table.id),
        table_number=table.number,
        party_size=party_size,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.SESSION,
                session_id,
                EventType.SESSION_OPENED,
                payload,
                event_id=session_id,
            )
        ],
        response={
            "id": str(session_id),
            "table_id": str(table.id),
            "table_number": table.number,
            "party_size": party_size,
            "bill_total_pesewas": 0,
            "paid_pesewas": 0,
            "balance_pesewas": 0,
        },
        status=201,
    )


def close_session(ctx: CommandContext, session_id: uuid.UUID) -> CommandOutcome:
    del ctx
    try:
        session = (
            TableSession.objects.select_for_update().select_related("table").get(pk=session_id)
        )
    except TableSession.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err

    if session.closed_at is not None:
        raise ApiError(409, ErrorCode.SESSION_CLOSED, "Session is already closed.")

    non_voided = Order.objects.filter(session_id=session.id).exclude(status=OrderStatus.VOIDED)
    if non_voided.exists() and session.settled_at is None:
        raise ApiError(
            409,
            ErrorCode.VALIDATION_ERROR,
            "Session can only be closed when settled or every order is voided.",
        )

    payload = SessionClosed(
        table_number=session.table.number,
        bill_total_pesewas=int(session.bill_total_pesewas),
        paid_pesewas=int(session.paid_pesewas),
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.SESSION,
                session.id,
                EventType.SESSION_CLOSED,
                payload,
            )
        ],
        response={
            "id": str(session.id),
            "closed": True,
            "bill_total_pesewas": int(session.bill_total_pesewas),
            "paid_pesewas": int(session.paid_pesewas),
        },
    )
