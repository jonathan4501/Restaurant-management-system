"""PIN failure counter and lockout. Redis key pin_fail:{device_id}, 15-minute TTL."""

from __future__ import annotations

import uuid

from django.conf import settings

from apps.core.publisher import client


def _key(device_id: uuid.UUID) -> str:
    return f"pin_fail:{device_id}"


def lockout_remaining_seconds(device_id: uuid.UUID) -> int | None:
    """Seconds until unlock if the device is locked; None if not locked."""
    redis = client()
    raw = redis.get(_key(device_id))
    if raw is None:
        return None
    if int(raw) < settings.PIN_MAX_FAILURES:
        return None
    ttl = redis.ttl(_key(device_id))
    return max(int(ttl), 0) if ttl is not None and ttl >= 0 else settings.PIN_LOCKOUT_SECONDS


def record_failure(device_id: uuid.UUID) -> tuple[int, int | None]:
    """
    Increment the failure counter. Returns (attempt_number, retry_after_seconds_if_now_locked).
    """
    redis = client()
    key = _key(device_id)
    count = int(redis.incr(key))
    if count == 1:
        redis.expire(key, settings.PIN_LOCKOUT_SECONDS)
    if count >= settings.PIN_MAX_FAILURES:
        ttl = redis.ttl(key)
        retry = max(int(ttl), 0) if ttl is not None and ttl >= 0 else settings.PIN_LOCKOUT_SECONDS
        # Ensure TTL stays at least the lockout window once locked.
        if (
            ttl is not None
            and 0 <= ttl < settings.PIN_LOCKOUT_SECONDS
            and count == settings.PIN_MAX_FAILURES
        ):
            redis.expire(key, settings.PIN_LOCKOUT_SECONDS)
            retry = settings.PIN_LOCKOUT_SECONDS
        return count, retry
    return count, None


def clear_failures(device_id: uuid.UUID) -> None:
    client().delete(_key(device_id))
