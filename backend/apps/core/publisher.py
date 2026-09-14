"""
Publish committed events to Redis for SSE fan-out. Called from transaction.on_commit.
A Redis failure is logged, never raised: the command has already committed, and clients recover
by replaying from `seq` on their next reconnect.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

import redis
from django.conf import settings

log = logging.getLogger(__name__)

_client: redis.Redis | None = None


def channel(restaurant_id: uuid.UUID) -> str:
    return f"events:{restaurant_id}"


def client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2
        )
    return _client


def publish(restaurant_id: uuid.UUID, envelopes: list[dict[str, Any]]) -> None:
    if not envelopes:
        return
    try:
        pipe = client().pipeline()
        for env in envelopes:
            pipe.publish(channel(restaurant_id), json.dumps(env, default=str))
        pipe.execute()
    except redis.RedisError:
        log.exception("event publish failed restaurant=%s count=%d", restaurant_id, len(envelopes))
