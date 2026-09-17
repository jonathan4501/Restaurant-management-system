"""
Authenticating the Raspberry Pi print bridge (WS12).

The bridge is a device with no human behind it: it presents `X-Device-Token` and no staff JWT, so
`accounts.principals.resolve_principal()` returns None for it and the middleware leaves the request
unauthenticated with no tenant in context. Printer routes therefore resolve the device themselves
and set the tenant context explicitly.

This is a deliberate local shim, not the long-term home for it — see "Requests to other
workstreams" in the WS12 pull request. It reuses `device_from_token` rather than re-implementing
the token hash, so there is exactly one place that knows how a device token is verified.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.http import HttpRequest

from apps.accounts.principals import AuthError, device_from_token
from apps.core.errors import ErrorCode
from apps.core.roles import DeviceRole

PRINTER_ROLE = str(DeviceRole.PRINTER)


@dataclass(frozen=True)
class PrinterPrincipal:
    """A print bridge. No actor_id: nothing it does is attributable to a person."""

    restaurant_id: UUID
    device_id: UUID
    label: str

    @property
    def stream_role(self) -> str:
        """The role the SSE filter uses. PRINTER sees ORDER + SESSION events."""
        return PRINTER_ROLE


def resolve_printer(request: HttpRequest) -> PrinterPrincipal:
    """
    The device behind this request, or AuthError.

    A device that has not been enrolled with `allowed_roles=['PRINTER']` is refused even if its
    token is valid — a waiter's tablet must not be able to pull every bill in the restaurant as
    printable bytes.
    """
    raw = request.headers.get("X-Device-Token")
    if not raw:
        raise AuthError(ErrorCode.DEVICE_UNKNOWN, "Printer requests need an X-Device-Token header.")
    device = device_from_token(raw)
    if PRINTER_ROLE not in (device.allowed_roles or []):
        raise AuthError(
            ErrorCode.ROLE_NOT_ALLOWED,
            "This device is not enrolled as a printer.",
        )
    return PrinterPrincipal(
        restaurant_id=device.restaurant_id,
        device_id=device.id,
        label=device.label,
    )
