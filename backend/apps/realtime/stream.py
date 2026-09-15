"""
Server-Sent Events over Redis pub/sub (ADR-0003). docs/08-backend-architecture.md §7.

Order of operations on connect matters: subscribe FIRST, then replay from the database, then forward
live messages skipping anything with seq <= the last one sent. That closes the gap between "what the
DB had" and "what Redis publishes next".

Replay is capped at one batch of SSE_REPLAY_LIMIT events. A longer gap is not replayed: the client
gets `event: RESYNC` carrying the current head seq, refetches its screen, and continues live.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db.models import Max

from apps.core.publisher import channel
from apps.core.tenancy import restaurant_context
from apps.orders.models import OrderEvent

from . import metrics
from .filters import visible_to

AuthCheck = Callable[[], Awaitable[bool]]


def format_sse(envelope: dict[str, Any]) -> str:
    return f"id: {envelope['seq']}\nevent: {envelope['type']}\ndata: {json.dumps(envelope, default=str)}\n\n"


def format_control(event: str, seq: int | None = None, **data: Any) -> str:
    """RESYNC / AUTH_EXPIRED. An `id:` line moves the client's Last-Event-ID forward."""
    head = f"id: {seq}\n" if seq is not None else ""
    body = {"seq": seq, **data} if seq is not None else data
    return f"{head}event: {event}\ndata: {json.dumps(body)}\n\n"


@dataclass(frozen=True)
class ReplayBatch:
    envelopes: list[dict[str, Any]]  # visible to the role, in seq order
    last_seq: int  # highest seq scanned, visible or not — the client's next `since`
    truncated: bool  # more events exist after last_seq


def replay_batch(
    restaurant_id: uuid.UUID, since: int, role: str, limit: int | None = None
) -> ReplayBatch:
    limit = limit or settings.SSE_REPLAY_LIMIT
    with restaurant_context(restaurant_id):
        events = list(OrderEvent.objects.filter(seq__gt=since).order_by("seq")[: limit + 1])
    truncated = len(events) > limit
    envelopes = [e.to_envelope() for e in events[:limit]]
    return ReplayBatch(
        envelopes=[env for env in envelopes if visible_to(role, env)],
        last_seq=envelopes[-1]["seq"] if envelopes else since,
        truncated=truncated,
    )


def replay(
    restaurant_id: uuid.UUID, since: int, role: str, limit: int | None = None
) -> list[dict[str, Any]]:
    return replay_batch(restaurant_id, since, role, limit).envelopes


def head_seq(restaurant_id: uuid.UUID) -> int:
    with restaurant_context(restaurant_id):
        return OrderEvent.objects.aggregate(head=Max("seq"))["head"] or 0


async def event_stream(
    restaurant_id: uuid.UUID,
    role: str,
    since: int | None,
    *,
    still_authorised: AuthCheck | None = None,
) -> AsyncIterator[str]:
    client = aioredis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    metrics.connected(restaurant_id, role)
    loop = asyncio.get_running_loop()
    try:
        await pubsub.subscribe(channel(restaurant_id))
        last = since
        if since is not None:
            batch = await sync_to_async(replay_batch)(restaurant_id, since, role)
            if batch.truncated:
                last = await sync_to_async(head_seq)(restaurant_id)
                yield format_control("RESYNC", last)
            else:
                for env in batch.envelopes:
                    yield format_sse(env)
                last = batch.last_seq

        next_auth_check = loop.time() + settings.SSE_AUTH_RECHECK_SECONDS
        while True:
            if still_authorised is not None and loop.time() >= next_auth_check:
                if not await still_authorised():
                    yield format_control("AUTH_EXPIRED", detail="Sign in again.")
                    return
                next_auth_check = loop.time() + settings.SSE_AUTH_RECHECK_SECONDS

            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=settings.SSE_HEARTBEAT_SECONDS
            )
            if message is None:
                yield ": keepalive\n\n"
                continue
            env = json.loads(message["data"])
            if last is not None and env["seq"] <= last:
                continue
            last = env["seq"]
            if visible_to(role, env):
                yield format_sse(env)
    except asyncio.CancelledError:
        pass
    finally:
        metrics.disconnected(restaurant_id, role)
        try:
            await pubsub.unsubscribe(channel(restaurant_id))
            await pubsub.aclose()
            await client.aclose()
        except Exception:
            pass
