"""
Asking for a receipt (WS12).

Printing a receipt is not a side effect, it is a recorded act. A reprinted receipt handed to a
second guest is fraud pattern 5 in docs/01-product-spec.md, so every request — first print or
reprint — appends RECEIPT_REQUESTED naming the actor, the device and whether paper had already been
produced for this bill.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.errors import ApiError, ErrorCode
from apps.core.roles import AggregateType
from apps.floor.models import TableSession
from apps.orders.events import EventType, ReceiptRequested
from apps.orders.models import OrderEvent


def _session_or_404(session_id: uuid.UUID) -> TableSession:
    try:
        return TableSession.objects.select_related("table").get(pk=session_id)
    except TableSession.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err


def already_printed(session_id: uuid.UUID) -> bool:
    return OrderEvent.objects.filter(
        aggregate_type=str(AggregateType.SESSION),
        aggregate_id=session_id,
        event_type=str(EventType.RECEIPT_REQUESTED),
    ).exists()


def request_receipt(ctx: CommandContext, data: dict[str, Any]) -> CommandOutcome:
    """POST /print/receipt — emits RECEIPT_REQUESTED so the bridge prints and the owner can see it."""
    session_id = data["session_id"]
    session = _session_or_404(session_id)
    reprint = already_printed(session.id)

    payload = ReceiptRequested(
        table_number=session.table.number,
        reprint=reprint,
    ).to_payload()

    return CommandOutcome(
        events=[
            EventDraft(
                AggregateType.SESSION,
                session.id,
                EventType.RECEIPT_REQUESTED,
                payload,
            )
        ],
        response={
            "session_id": str(session.id),
            "table_number": session.table.number,
            "reprint": reprint,
        },
        status=201,
    )
