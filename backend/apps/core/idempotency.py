"""
Idempotency-Key semantics (docs/08 §3):

    claim()    insert IN_PROGRESS in its own transaction
               conflict + DONE + same hash      → Replay
               conflict + DONE + different hash → 422 idempotency_key_reused
               conflict + IN_PROGRESS, fresh    → 409 idempotency_in_progress
               conflict + IN_PROGRESS, stale    → take over
    complete() store the response inside the command transaction
    release()  drop the claim after an unexpected failure so the client can retry
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .errors import ApiError, ErrorCode
from .models import IdempotencyKey


@dataclass(frozen=True)
class Replay:
    status: int
    body: Any


@dataclass(frozen=True)
class Claimed:
    row_id: uuid.UUID


def request_hash(method: str, path: str, body: Any) -> str:
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{method.upper()} {path}\n{canonical}".encode()).hexdigest()


def claim(restaurant_id: uuid.UUID, key: uuid.UUID, req_hash: str) -> Replay | Claimed:
    try:
        with transaction.atomic():
            row = IdempotencyKey.objects.unscoped().create(
                restaurant_id=restaurant_id, key=key, request_hash=req_hash
            )
            return Claimed(row.id)
    except IntegrityError:
        pass

    row = IdempotencyKey.objects.unscoped().get(restaurant_id=restaurant_id, key=key)
    if row.status == IdempotencyKey.Status.DONE:
        if row.request_hash != req_hash:
            raise ApiError(
                422,
                ErrorCode.IDEMPOTENCY_KEY_REUSED,
                "This Idempotency-Key was already used for a different request.",
            )
        return Replay(int(row.response_status or 200), row.response_body)

    takeover_after = timedelta(seconds=settings.IDEMPOTENCY_IN_PROGRESS_TAKEOVER_SECONDS)
    if timezone.now() - row.created_at < takeover_after:
        raise ApiError(
            409,
            ErrorCode.IDEMPOTENCY_IN_PROGRESS,
            "A request with this Idempotency-Key is still being processed.",
        )

    # Stale claim: the earlier attempt died before completing. Take it over.
    IdempotencyKey.objects.unscoped().filter(pk=row.pk).update(
        request_hash=req_hash, created_at=timezone.now()
    )
    return Claimed(row.id)


def complete(row_id: uuid.UUID, status: int, body: Any) -> None:
    IdempotencyKey.objects.unscoped().filter(pk=row_id).update(
        status=IdempotencyKey.Status.DONE, response_status=status, response_body=body
    )


def release(row_id: uuid.UUID) -> None:
    """Only after an unexpected (5xx) failure. Domain rejections (4xx) are completed, not released."""
    IdempotencyKey.objects.unscoped().filter(
        pk=row_id, status=IdempotencyKey.Status.IN_PROGRESS
    ).delete()
