"""
The one write path. docs/08-backend-architecture.md §1.

    run_command(ctx, handler)
        1. claim the Idempotency-Key, or replay
        2. transaction.atomic()
        3. pg_advisory_xact_lock(restaurant)     — appends serialised per tenant, seq gapless
        4. handler(ctx) → CommandOutcome         — locks its aggregate, validates, returns EventDrafts
        5. append events with seq = last + 1
        6. projections.apply(event) for each
        7. complete the idempotency row
        8. on_commit → publish envelopes to Redis
"""

from __future__ import annotations

import logging
import uuid
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone

from . import idempotency, projections, publisher
from .errors import ApiError
from .roles import ActorRole, AggregateType
from .uuid7 import uuid7

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandContext:
    restaurant_id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_role: ActorRole
    device_id: uuid.UUID | None
    idempotency_key: uuid.UUID
    request_hash: str
    client_created_at: datetime
    authorised_by: uuid.UUID | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class EventDraft:
    aggregate_type: AggregateType
    aggregate_id: uuid.UUID
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    order_id: uuid.UUID | None = None
    event_id: uuid.UUID | None = None  # client-supplied UUIDv7 when the client originated it
    reason_code: str | None = None  # overrides ctx.reason_code for this event only


@dataclass
class CommandOutcome:
    events: list[EventDraft]
    response: Any
    status: int = 200


@dataclass(frozen=True)
class CommandResponse:
    status: int
    body: Any
    replayed: bool = False


Handler = Callable[[CommandContext], CommandOutcome]


def advisory_lock_key(restaurant_id: uuid.UUID) -> int:
    """Stable 63-bit key for pg_advisory_xact_lock, derived from the restaurant id."""
    return zlib.crc32(restaurant_id.bytes) & 0x7FFFFFFF


def acquire_restaurant_lock(restaurant_id: uuid.UUID) -> None:
    with connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [advisory_lock_key(restaurant_id)])


def run_command(ctx: CommandContext, handler: Handler) -> CommandResponse:
    claim = idempotency.claim(ctx.restaurant_id, ctx.idempotency_key, ctx.request_hash)
    if isinstance(claim, idempotency.Replay):
        return CommandResponse(claim.status, claim.body, replayed=True)

    try:
        with transaction.atomic():
            acquire_restaurant_lock(ctx.restaurant_id)
            outcome = handler(ctx)
            events = _append_events(ctx, outcome.events)
            for event in events:
                projections.apply(event)
            idempotency.complete(claim.row_id, outcome.status, outcome.response)
            envelopes = [event.to_envelope() for event in events]
            transaction.on_commit(lambda: publisher.publish(ctx.restaurant_id, envelopes))
            return CommandResponse(outcome.status, outcome.response)
    except ApiError as err:
        # A domain rejection is a deterministic answer. The transaction above has rolled back, so
        # store the 4xx now (own transaction) and a replay of the same key gets the same answer.
        idempotency.complete(claim.row_id, err.status_code, err.as_problem())
        raise
    except Exception:
        idempotency.release(claim.row_id)
        raise


def _append_events(ctx: CommandContext, drafts: list[EventDraft]) -> list[Any]:
    if not drafts:
        return []
    from apps.orders.models import OrderEvent

    last = (
        OrderEvent.objects.unscoped()
        .filter(restaurant_id=ctx.restaurant_id)
        .aggregate(m=Max("seq"))["m"]
        or 0
    )
    now = timezone.now()
    rows = []
    for offset, draft in enumerate(drafts, start=1):
        rows.append(
            OrderEvent(
                id=draft.event_id or uuid7(),
                restaurant_id=ctx.restaurant_id,
                seq=last + offset,
                aggregate_type=str(draft.aggregate_type),
                aggregate_id=draft.aggregate_id,
                order_id=draft.order_id,
                event_type=str(draft.event_type),
                payload=draft.payload,
                actor_id=ctx.actor_id,
                actor_role=str(ctx.actor_role),
                authorised_by_id=ctx.authorised_by,
                reason_code=draft.reason_code or ctx.reason_code,
                device_id=ctx.device_id,
                idempotency_key=ctx.idempotency_key,
                client_created_at=ctx.client_created_at,
                created_at=now,
            )
        )
    OrderEvent.objects.unscoped().bulk_create(rows)
    return rows
