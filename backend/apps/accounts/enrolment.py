"""Device enrolment codes: 8 chars, 15-minute expiry. Displayed as XXXX-XXXX."""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.utils import timezone

from .models import Device

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I
ENROLMENT_TTL = timedelta(minutes=15)


def normalize_enrolment_code(code: str) -> str:
    return code.replace("-", "").replace(" ", "").upper()


def format_enrolment_code(raw: str) -> str:
    raw = normalize_enrolment_code(raw)
    if len(raw) != 8:
        raise ValueError("enrolment code must be 8 characters")
    return f"{raw[:4]}-{raw[4:]}"


def new_enrolment_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(8))
    return format_enrolment_code(raw)


def assign_enrolment_code(device: Device) -> str:
    """Set a fresh one-time enrolment code on the device. Returns the code to show once."""
    code = new_enrolment_code()
    device.enrolment_code = normalize_enrolment_code(code)
    device.enrolment_expires_at = timezone.now() + ENROLMENT_TTL
    device.save(update_fields=["enrolment_code", "enrolment_expires_at"])
    return code
