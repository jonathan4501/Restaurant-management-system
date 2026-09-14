"""
Manager authorisation tokens: single use, 60 s, bound to a device and a purpose.
Issued by POST /auth/authorise (WS01); consumed here by CommandView.
"""

from __future__ import annotations

import json
import secrets
import uuid

from django.conf import settings

from apps.core.errors import ApiError, ErrorCode
from apps.core.publisher import client
from apps.core.roles import AuthorisationPurpose


def _key(token: str) -> str:
    return f"auth:{token}"


def issue_authorisation(
    *, staff_id: uuid.UUID, device_id: uuid.UUID | None, purpose: AuthorisationPurpose
) -> str:
    token = secrets.token_urlsafe(24)
    client().set(
        _key(token),
        json.dumps(
            {
                "staff_id": str(staff_id),
                "device_id": str(device_id) if device_id else None,
                "purpose": purpose,
            }
        ),
        ex=settings.AUTHORISATION_TOKEN_TTL_SECONDS,
    )
    return token


def consume_authorisation(
    token: str, *, device_id: uuid.UUID | None, purpose: AuthorisationPurpose
) -> uuid.UUID:
    raw = client().getdel(_key(token))
    if not raw:
        raise ApiError(
            403,
            ErrorCode.AUTHORISATION_INVALID,
            "Authorisation token is invalid, used, or expired.",
        )
    data = json.loads(raw)
    if data["purpose"] != purpose:
        raise ApiError(
            403,
            ErrorCode.AUTHORISATION_PURPOSE_MISMATCH,
            f"Authorisation was granted for {data['purpose']}, not {purpose}.",
        )
    if data["device_id"] and device_id and data["device_id"] != str(device_id):
        raise ApiError(
            403, ErrorCode.AUTHORISATION_INVALID, "Authorisation was granted on a different device."
        )
    return uuid.UUID(data["staff_id"])
