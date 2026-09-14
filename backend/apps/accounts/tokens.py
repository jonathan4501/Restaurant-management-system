"""
Tokens. Issuance endpoints are WS01; this module is the shared vocabulary so that verification
(needed by WS00's principal resolution) and issuance agree by construction.

    device token   opaque 32-byte urlsafe, stored as sha256, header X-Device-Token
    staff JWT      HS256, 12 h, {sub, role, rid, did, jti}
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

ALGORITHM = "HS256"


def new_device_token() -> tuple[str, str]:
    """Returns (token, sha256 hex). Store the hash, return the token once."""
    token = secrets.token_urlsafe(32)
    return token, hash_device_token(token)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue(claims: dict[str, Any], ttl_seconds: int) -> str:
    now = datetime.now(UTC)
    payload = {
        **claims,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.JWT_SIGNING_KEY, algorithm=ALGORITHM)


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
        return jwt.decode(token, settings.JWT_SIGNING_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as err:
        raise TokenError("token_expired", "Token has expired.") from err
    except jwt.InvalidTokenError as err:
        raise TokenError("token_invalid", "Token is not valid.") from err
