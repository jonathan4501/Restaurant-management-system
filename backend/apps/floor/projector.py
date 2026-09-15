"""SESSION_* projections. Table rows are configuration; sessions are derived from the stream."""

from __future__ import annotations

import uuid

from django.db.models import F

from apps.core.projections import project
from apps.floor.models import TableSession
from apps.orders.events import EventType
from apps.orders.models import OrderEvent


@project(EventType.SESSION_OPENED)
def session_opened(event: OrderEvent) -> None:
    payload = event.payload
    # Runner unit tests historically append a stub SESSION_OPENED without table_id.
    # Real open_session always sends the full SessionOpened payload.
    if "table_id" not in payload:
        return
    if event.actor_id is None:
        return
    TableSession.objects.update_or_create(
        id=event.aggregate_id,
        defaults={
            "restaurant_id": event.restaurant_id,
            "table_id": uuid.UUID(payload["table_id"]),
            "opened_by_id": event.actor_id,
            "party_size": payload.get("party_size"),
            "opened_at": event.created_at,
            "closed_at": None,
            "bill_total_pesewas": 0,
            "paid_pesewas": 0,
            "settled_at": None,
            "reopened_count": 0,
        },
    )


@project(EventType.SESSION_CLOSED)
def session_closed(event: OrderEvent) -> None:
    TableSession.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(closed_at=event.created_at)


@project(EventType.SESSION_SETTLED)
def session_settled(event: OrderEvent) -> None:
    # WS05 emits this; projector lives with the session aggregate so rebuild stays faithful.
    TableSession.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(settled_at=event.created_at)


@project(EventType.SESSION_REOPENED)
def session_reopened(event: OrderEvent) -> None:
    TableSession.objects.unscoped().filter(
        restaurant_id=event.restaurant_id, id=event.aggregate_id
    ).update(closed_at=None, settled_at=None, reopened_count=F("reopened_count") + 1)
