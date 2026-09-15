"""Per-restaurant menu body cache + ETag. Invalidated on every menu write."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from django.core.cache import cache

CACHE_TTL_SECONDS = 60 * 60  # 1 hour; writes always invalidate


def _body_key(restaurant_id: uuid.UUID) -> str:
    return f"menu:v1:{restaurant_id}"


def _etag_key(restaurant_id: uuid.UUID) -> str:
    return f"menu:v1:{restaurant_id}:etag"


def compute_etag(body: dict[str, Any]) -> str:
    """sha256 of the canonical JSON body. Returned to clients as a quoted ETag."""
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def quote_etag(etag: str) -> str:
    return f'"{etag}"'


def get_cached_menu(restaurant_id: uuid.UUID) -> tuple[dict[str, Any], str] | None:
    body = cache.get(_body_key(restaurant_id))
    etag = cache.get(_etag_key(restaurant_id))
    if body is None or etag is None:
        return None
    return body, etag


def set_cached_menu(restaurant_id: uuid.UUID, body: dict[str, Any], etag: str) -> None:
    cache.set(_body_key(restaurant_id), body, timeout=CACHE_TTL_SECONDS)
    cache.set(_etag_key(restaurant_id), etag, timeout=CACHE_TTL_SECONDS)


def invalidate_menu_cache(restaurant_id: uuid.UUID) -> None:
    cache.delete_many([_body_key(restaurant_id), _etag_key(restaurant_id)])
