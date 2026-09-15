"""
Who is calling. docs/08-backend-architecture.md §6.

resolve_principal() is called by RequestContextMiddleware (so the tenant context is set before any
view runs) and by the SSE view. PrincipalAuthentication is the DRF adapter that surfaces the result.

DeviceStaffAuthentication / GuestAuthentication / OwnerSessionAuthentication are the named classes
from the architecture doc; they share the same Principal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from django.http import HttpRequest
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, SessionAuthentication
from rest_framework.request import Request

from apps.core.errors import ApiError, ErrorCode
from apps.core.roles import ActorRole
from apps.core.tenancy import restaurant_context

from .enrolment import normalize_enrolment_code
from .models import Device, Staff
from .tokens import TokenError, decode, hash_device_token

if TYPE_CHECKING:
    from apps.floor.models import Table


@dataclass(frozen=True)
class Principal:
    kind: Literal["STAFF", "GUEST", "OWNER", "SYSTEM"]
    restaurant_id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_role: ActorRole
    device_id: uuid.UUID | None
    session_id: uuid.UUID | None = None  # GUEST only

    # DRF compatibility: request.user is this object.
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False


class AuthError(Exception):
    def __init__(self, code: ErrorCode | str, detail: str) -> None:
        super().__init__(detail)
        self.code = str(code)
        self.detail = detail


def _bearer(request: HttpRequest) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token else None


def device_from_token(raw: str) -> Device:
    """Resolve an enrolled device by its opaque token. Uses unscoped (allow-listed file)."""
    device = Device.objects.unscoped().filter(token_hash=hash_device_token(raw)).first()
    if device is None:
        raise AuthError(ErrorCode.DEVICE_UNKNOWN, "Device is not enrolled.")
    if device.is_revoked:
        raise AuthError(ErrorCode.DEVICE_REVOKED, "Device has been revoked.")
    return device


def device_from_request(request: HttpRequest) -> Device | None:
    raw = request.headers.get("X-Device-Token")
    if not raw:
        return None
    return device_from_token(raw)


def find_device_by_enrolment_code(code: str) -> Device | None:
    """Lookup pending enrolment by code. Unscoped — no tenant yet."""
    normalized = normalize_enrolment_code(code)
    if not normalized:
        return None
    return (
        Device.objects.unscoped().filter(enrolment_code=normalized, revoked_at__isnull=True).first()
    )


def find_table_by_qr_token(qr_token: str) -> Table | None:
    from apps.floor.models import Table

    return Table.objects.unscoped().filter(qr_token=qr_token, is_active=True).first()


def find_owner_staff_by_email(email: str) -> Staff | None:
    return (
        Staff.objects.unscoped()
        .filter(email__iexact=email.strip(), role="OWNER", is_active=True)
        .select_related("user")
        .first()
    )


def _device(request: HttpRequest) -> Device | None:
    return device_from_request(request)


def _guest_session_open(restaurant_id: uuid.UUID, session_id: uuid.UUID) -> None:
    """401 only when the session exists and is closed. Missing rows are left to guest views (404)."""
    from apps.floor.models import TableSession

    with restaurant_context(restaurant_id):
        session = TableSession.objects.filter(id=session_id).first()
    if session is not None and session.closed_at is not None:
        raise AuthError(ErrorCode.SESSION_CLOSED, "This table session is closed.")


def resolve_principal(request: HttpRequest) -> Principal | None:
    """None when no credentials are present. Raises AuthError when credentials are present but bad."""
    device = _device(request)
    token = _bearer(request)

    if token is None:
        # Owner session (django.contrib.auth + OTP) — used by the admin and the owner API.
        user = getattr(request, "user", None)
        staff = getattr(user, "staff", None) if user is not None and user.is_authenticated else None
        if staff is not None and staff.role == "OWNER" and staff.is_active:
            is_verified = getattr(user, "is_verified", lambda: False)
            if not is_verified():
                return None
            return Principal("OWNER", staff.restaurant_id, staff.id, ActorRole.OWNER, None)
        return None

    try:
        claims = decode(token)
    except TokenError as err:
        raise AuthError(err.code, err.detail) from err

    restaurant_id = uuid.UUID(claims["rid"])

    if claims.get("kind") == "GUEST":
        session_id = uuid.UUID(claims["sid"])
        _guest_session_open(restaurant_id, session_id)
        return Principal("GUEST", restaurant_id, None, ActorRole.GUEST, None, session_id=session_id)

    if claims.get("kind") != "STAFF":
        raise AuthError(ErrorCode.TOKEN_INVALID, "Unknown token kind.")
    if device is None:
        raise AuthError(
            ErrorCode.DEVICE_UNKNOWN, "Staff requests must come from an enrolled device."
        )
    if str(device.id) != claims.get("did") or device.restaurant_id != restaurant_id:
        raise AuthError(ErrorCode.TOKEN_INVALID, "Token was issued for a different device.")

    staff = (
        Staff.objects.unscoped()
        .filter(id=uuid.UUID(claims["sub"]), restaurant_id=restaurant_id, is_active=True)
        .first()
    )
    if staff is None:
        raise AuthError(ErrorCode.TOKEN_INVALID, "Staff member not found or inactive.")

    _touch_device(device)
    return Principal("STAFF", restaurant_id, staff.id, ActorRole(staff.role), device.id)


def _touch_device(device: Device) -> None:
    now = timezone.now()
    if device.last_seen_at is None or (now - device.last_seen_at).total_seconds() > 60:
        Device.objects.unscoped().filter(pk=device.pk).update(last_seen_at=now)


def current_principal(request: object) -> Principal:
    """The principal the middleware attached to this request. Views call this instead of request.principal."""
    principal = getattr(request, "principal", None)
    if principal is None:
        raise ApiError(401, ErrorCode.TOKEN_INVALID, "Authentication required.")
    return principal


class PrincipalAuthentication(BaseAuthentication):
    """DRF adapter: the middleware already resolved request.principal; surface it or fail."""

    def authenticate(self, request: Request) -> tuple[Principal, Principal] | None:
        err = getattr(request._request, "auth_error", None)
        if err is not None:
            exc = exceptions.AuthenticationFailed(err.detail)
            exc.code = err.code  # type: ignore[attr-defined]
            raise exc
        principal = getattr(request._request, "principal", None)
        if principal is None:
            return None
        return principal, principal

    def authenticate_header(self, request: Request) -> str:
        return "Bearer"


# Architecture aliases (08 §6).
DeviceStaffAuthentication = PrincipalAuthentication


class GuestAuthentication(PrincipalAuthentication):
    """Only accepts a GUEST principal. Used on /api/v1/guest/… routes."""

    def authenticate(self, request: Request) -> tuple[Principal, Principal] | None:
        result = super().authenticate(request)
        if result is None:
            return None
        principal, _ = result
        if principal.kind != "GUEST":
            raise exceptions.PermissionDenied("Guest routes require a guest token.")
        return result


class OwnerSessionAuthentication(SessionAuthentication):
    """Django session + django-otp verified; surfaces an OWNER Principal."""

    def authenticate(self, request: Request) -> tuple[Principal, Principal] | None:
        # Middleware already resolved a verified OWNER — trust it.
        existing = getattr(request._request, "principal", None)
        if existing is not None and existing.kind == "OWNER":
            return existing, existing

        django_request = request._request
        user = getattr(django_request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None

        # Authenticated owner session but TOTP not verified yet.
        staff = getattr(user, "staff", None)
        is_verified = getattr(user, "is_verified", lambda: False)
        if staff is not None and staff.role == "OWNER" and staff.is_active and not is_verified():
            exc = exceptions.AuthenticationFailed("TOTP verification required.")
            exc.code = ErrorCode.TOKEN_INVALID  # type: ignore[attr-defined]
            raise exc

        result = super().authenticate(request)
        if result is None:
            return None

        user, _auth = result
        is_verified = getattr(user, "is_verified", lambda: False)
        if not is_verified():
            exc = exceptions.AuthenticationFailed("TOTP verification required.")
            exc.code = ErrorCode.TOKEN_INVALID  # type: ignore[attr-defined]
            raise exc

        staff = getattr(user, "staff", None)
        if staff is None or staff.role != "OWNER" or not staff.is_active:
            exc = exceptions.AuthenticationFailed("Owner account required.")
            exc.code = ErrorCode.TOKEN_INVALID  # type: ignore[attr-defined]
            raise exc

        principal = Principal("OWNER", staff.restaurant_id, staff.id, ActorRole.OWNER, None)
        request._request.principal = principal  # type: ignore[attr-defined]
        return principal, principal
