"""Staff JWT jti registry in Redis — logout revokes by deleting the key."""

from __future__ import annotations

from django.conf import settings

from apps.core.publisher import client


def _key(jti: str) -> str:
    return f"jti:{jti}"


def register_jti(jti: str, *, ttl_seconds: int | None = None) -> None:
    client().set(_key(jti), "1", ex=ttl_seconds or settings.STAFF_TOKEN_TTL_SECONDS)


def revoke_jti(jti: str) -> None:
    client().delete(_key(jti))


def jti_is_active(jti: str) -> bool:
    return bool(client().exists(_key(jti)))
