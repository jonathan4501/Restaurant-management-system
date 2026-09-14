"""
Server-Sent Events over Redis pub/sub (ADR-0003). docs/08-backend-architecture.md §7.

Order of operations on connect matters: subscribe FIRST, then replay from the database, then forward
live messages skipping anything with seq <= the last one sent. That closes the gap between "what the
DB had" and "what Redis publishes next".
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
from asgiref.sync import sync_to_async
from django.conf import settings

from apps.core.publisher import channel
from apps.core.tenancy import restaurant_context
from apps.orders.models import OrderEvent

from .filters import visible_to


def format_sse(envelope: dict[str, Any]) -> str:
    return f"id: {envelope['seq']}\nevent: {envelope['type']}\ndata: {json.dumps(envelope, default=str)}\n\n"


def replay(
    restaurant_id: uuid.UUID, since: int, role: str, limit: int | None = None
) -> list[dict[str, Any]]:
    limit = limit or settings.SSE_REPLAY_LIMIT
    with restaurant_context(restaurant_id):
        events = OrderEvent.objects.filter(seq__gt=since).order_by("seq")[:limit]
        return [env for env in (e.to_envelope() for e in events) if visible_to(role, env)]


async def event_stream(
    restaurant_id: uuid.UUID, role: str, since: int | None
) -> AsyncIterator[str]:
    client = aioredis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub()
    await pubsub.subscribe(channel(restaurant_id))
    last = since
    try:
        if since is not None:
            for env in await sync_to_async(replay)(restaurant_id, since, role):
                last = env["seq"]
                yield format_sse(env)
            if last is not None and last - since >= settings.SSE_REPLAY_LIMIT:
                yield "event: RESYNC\ndata: {}\n\n"

        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=settings.SSE_HEARTBEAT_SECONDS
            )
            if message is None:
                yield ": keepalive\n\n"
                continue
            env = json.loads(message["data"])
            if last is not None and env["seq"] <= last:
                continue
            if not visible_to(role, env):
                last = env["seq"]
                continue
            last = env["seq"]
            yield format_sse(env)
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await pubsub.unsubscribe(channel(restaurant_id))
            await pubsub.aclose()
            await client.aclose()
        except Exception:
            pass
