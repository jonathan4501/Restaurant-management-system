"""
Tokens. Issuance and verification agree by construction.

    device token   opaque 32-byte urlsafe, stored as sha256, header X-Device-Token
    staff JWT      HS256, 12 h, {sub, role, rid, did, jti}; jti registered in Redis
    guest JWT      HS256, 2 h,  {sid, rid, role: GUEST, mode}
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from django.conf import settings

from .jwt_sessions import jti_is_active, register_jti

ALGORITHM = "HS256"


def new_device_token() -> tuple[str, str]:
    """Returns (token, sha256 hex). Store the hash, return the token once."""
    token = secrets.token_urlsafe(32)
    return token, hash_device_token(token)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue(claims: dict[str, Any], ttl_seconds: int, *, register: bool = False) -> str:
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {
        **claims,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": jti,
    }
    token = jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)
    if register:
        register_jti(jti, ttl_seconds=ttl_seconds)
    return token


def issue_staff_token(
    *, staff_id: uuid.UUID, role: str, restaurant_id: uuid.UUID, device_id: uuid.UUID
) -> str:
    return _issue(
        {
            "kind": "STAFF",
            "sub": str(staff_id),
            "role": role,
            "rid": str(restaurant_id),
            "did": str(device_id),
        },
        settings.STAFF_TOKEN_TTL_SECONDS,
        register=True,
    )


def issue_guest_token(*, session_id: uuid.UUID, restaurant_id: uuid.UUID, mode: str) -> str:
    return _issue(
        {
            "kind": "GUEST",
            "sid": str(session_id),
            "rid": str(restaurant_id),
            "role": "GUEST",
            "mode": mode,
        },
        settings.GUEST_TOKEN_TTL_SECONDS,
    )


class TokenError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def decode(token: str) -> dict[str, Any]:
    try:
        claims = jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as err:
        raise TokenError("token_expired", "Token has expired.") from err
    except jwt.InvalidTokenError as err:
        raise TokenError("token_invalid", "Token is not valid.") from err

    if claims.get("kind") == "STAFF":
        jti = claims.get("jti")
        if not jti or not jti_is_active(str(jti)):
            raise TokenError("token_invalid", "Token has been revoked.")
    return claims


def staff_token_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(seconds=settings.STAFF_TOKEN_TTL_SECONDS)
