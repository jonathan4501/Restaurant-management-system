"""
Auth and device endpoints. docs/09-api-contract.md §Auth and devices.

Writes that emit events go through run_command. Views that establish a principal before one exists
subclass CommandView (so the Idempotency-Key invariant holds) and override post().
"""

from __future__ import annotations

import uuid
from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user as django_get_user
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.commands import CommandContext, CommandOutcome, EventDraft, run_command
from apps.core.errors import ApiError, ErrorCode, problem
from apps.core.idempotency import request_hash
from apps.core.permissions import RolePermission
from apps.core.roles import (
    MANAGER_ROLES,
    STAFF_ROLES,
    ActorRole,
    AggregateType,
    AuthorisationPurpose,
)
from apps.core.tenancy import restaurant_context
from apps.core.views import CommandView, parse_client_time, parse_idempotency_key
from apps.floor.models import TableSession
from apps.orders.events import EventType

from .authorisation import issue_authorisation
from .jwt_sessions import revoke_jti
from .models import Device, Staff
from .pin_lockout import clear_failures, lockout_remaining_seconds, record_failure
from .pins import verify_pin
from .principals import (
    AuthError,
    GuestAuthentication,
    OwnerSessionAuthentication,
    current_principal,
    device_from_request,
    find_device_by_enrolment_code,
    find_owner_staff_by_email,
    find_table_by_qr_token,
)
from .serializers import (
    AuthoriseInput,
    EnrolDeviceInput,
    GuestTokenInput,
    OwnerLoginInput,
    OwnerTotpInput,
    PinLoginInput,
)
from .throttles import GuestThrottle
from .tokens import (
    TokenError,
    decode,
    issue_guest_token,
    issue_staff_token,
    new_device_token,
    staff_token_expires_at,
)


def _django_request(request: Request) -> Any:
    """Session auth must run on the underlying Django HttpRequest, not the DRF wrapper."""
    return getattr(request, "_request", request)


class PassiveSessionAuthentication(BaseAuthentication):
    """
    Load the Django session user without CSRF (owner login/totp establish the session).
    Prevents DRF from overwriting request.user with UNAUTHENTICATED_USER=None.
    """

    def authenticate(self, request: Request) -> tuple[Any, None] | None:
        django_request = _django_request(request)
        user = django_get_user(django_request)
        if not user.is_authenticated:
            return None
        django_request.user = user
        return user, None


def _bearer_jti(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        return str(decode(token.strip()).get("jti") or "") or None
    except TokenError:
        return None


def _ctx(
    request: Request,
    *,
    restaurant_id: uuid.UUID,
    actor_role: ActorRole,
    actor_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
) -> CommandContext:
    body = request.data if isinstance(request.data, dict) else {}
    return CommandContext(
        restaurant_id=restaurant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        device_id=device_id,
        idempotency_key=parse_idempotency_key(request),
        request_hash=request_hash(request.method or "POST", request.path, body),
        client_created_at=parse_client_time(request),
    )


def _problem_response(
    status_code: int, code: ErrorCode | str, detail: str, **extra: Any
) -> Response:
    return Response(
        problem(status_code, str(code), detail, **extra),
        status=status_code,
        content_type="application/problem+json",
    )


class EnrolDeviceView(CommandView):
    """POST /devices/enrol — exchange a one-time enrolment code for a device token."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    input_serializer = EnrolDeviceInput

    def post(self, request: Request, **kwargs: Any) -> Response:
        ser = EnrolDeviceInput(data=request.data)
        ser.is_valid(raise_exception=True)
        code = ser.validated_data["enrolment_code"]

        device = find_device_by_enrolment_code(code)
        if device is None:
            raise ApiError(400, ErrorCode.VALIDATION_ERROR, "Enrolment code is not valid.")
        if device.enrolment_expires_at is None or device.enrolment_expires_at < timezone.now():
            raise ApiError(400, ErrorCode.VALIDATION_ERROR, "Enrolment code has expired.")
        if device.token_hash is not None:
            raise ApiError(400, ErrorCode.VALIDATION_ERROR, "Enrolment code has already been used.")

        token, token_hash = new_device_token()
        now = timezone.now()

        def handler(ctx: CommandContext) -> CommandOutcome:
            Device.objects.filter(pk=device.pk).update(
                token_hash=token_hash,
                enrolled_at=now,
                enrolment_code=None,
                enrolment_expires_at=None,
                last_seen_at=now,
            )
            return CommandOutcome(
                events=[
                    EventDraft(
                        AggregateType.DEVICE,
                        device.id,
                        EventType.DEVICE_ENROLLED,
                        {"label": device.label, "allowed_roles": list(device.allowed_roles)},
                    )
                ],
                response={
                    "device_id": str(device.id),
                    "device_token": token,
                    "allowed_roles": list(device.allowed_roles),
                },
                status=200,
            )

        with restaurant_context(device.restaurant_id):
            result = run_command(
                _ctx(request, restaurant_id=device.restaurant_id, actor_role=ActorRole.SYSTEM),
                handler,
            )
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class DeviceMeView(APIView):
    """
    GET /devices/me — device label, roles, staff list for the PIN pad.

    Answers to the device token alone: the PIN pad needs the staff list before anyone has signed in.
    A staff bearer, if sent, must still be valid (a revoked or foreign token is 401). Guests are 403.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        principal = getattr(request._request, "principal", None)
        if principal is not None and principal.actor_role == ActorRole.GUEST:
            raise ApiError(
                403, ErrorCode.ROLE_NOT_ALLOWED, "This role may not perform this action."
            )
        try:
            device = device_from_request(request._request)
        except AuthError as err:
            raise ApiError(401, err.code, err.detail) from err
        if device is None:
            raise ApiError(401, ErrorCode.DEVICE_UNKNOWN, "Device is required.")

        with restaurant_context(device.restaurant_id):
            staff_rows = list(
                Staff.objects.filter(is_active=True, role__in=device.allowed_roles)
                .order_by("full_name")
                .values("id", "full_name", "role")
            )
        return Response(
            {
                "device_id": str(device.id),
                "label": device.label,
                "allowed_roles": list(device.allowed_roles),
                "staff": [
                    {"id": str(s["id"]), "name": s["full_name"], "role": s["role"]}
                    for s in staff_rows
                ],
            }
        )


class PinLoginView(CommandView):
    """POST /auth/pin — device + staff PIN → staff JWT."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    input_serializer = PinLoginInput

    def post(self, request: Request, **kwargs: Any) -> Response:
        err = getattr(request, "auth_error", None) or getattr(
            getattr(request, "_request", request), "auth_error", None
        )
        if err is not None:
            return _problem_response(401, err.code, err.detail)

        try:
            device = device_from_request(request)
        except AuthError as auth_err:
            return _problem_response(401, auth_err.code, auth_err.detail)
        if device is None:
            raise ApiError(401, ErrorCode.DEVICE_UNKNOWN, "X-Device-Token is required.")

        ser = PinLoginInput(data=request.data)
        ser.is_valid(raise_exception=True)
        staff_id: uuid.UUID = ser.validated_data["staff_id"]
        pin: str = ser.validated_data["pin"]

        remaining = lockout_remaining_seconds(device.id)
        if remaining is not None:
            raise ApiError(
                423,
                ErrorCode.PIN_LOCKED,
                "Too many PIN failures. Try again later.",
                extra={"retry_after_seconds": remaining},
            )

        with restaurant_context(device.restaurant_id):
            staff = Staff.objects.filter(id=staff_id, is_active=True).first()
            if staff is None or staff.role not in device.allowed_roles:
                # Count as a failure without revealing whether the staff exists.
                return self._fail(request, device, staff_id=None)

            if not verify_pin(staff.pin_hash, pin):
                return self._fail(request, device, staff_id=staff.id)

            clear_failures(device.id)
            token = issue_staff_token(
                staff_id=staff.id,
                role=staff.role,
                restaurant_id=device.restaurant_id,
                device_id=device.id,
            )
            Device.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())

            # Successful login is not an event; still go through the idempotency key.
            result = run_command(
                _ctx(
                    request,
                    restaurant_id=device.restaurant_id,
                    actor_id=staff.id,
                    actor_role=ActorRole(staff.role),
                    device_id=device.id,
                ),
                lambda ctx: CommandOutcome(
                    events=[],
                    response={
                        "token": token,
                        "expires_at": staff_token_expires_at().isoformat().replace("+00:00", "Z"),
                        "staff": {"id": str(staff.id), "name": staff.full_name, "role": staff.role},
                    },
                ),
            )
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response

    def _fail(self, request: Request, device: Device, *, staff_id: uuid.UUID | None) -> Response:
        attempt, locked_for = record_failure(device.id)

        def handler(ctx: CommandContext) -> CommandOutcome:
            events = [
                EventDraft(
                    AggregateType.DEVICE,
                    device.id,
                    EventType.PIN_FAILED,
                    {
                        "staff_id": str(staff_id) if staff_id else None,
                        "attempt": attempt,
                    },
                )
            ]
            if locked_for is not None:
                events.append(
                    EventDraft(
                        AggregateType.DEVICE,
                        device.id,
                        EventType.PIN_LOCKED,
                        {"lockout_seconds": settings.PIN_LOCKOUT_SECONDS},
                    )
                )
                body = problem(
                    423,
                    ErrorCode.PIN_LOCKED,
                    "Too many PIN failures. Try again later.",
                    retry_after_seconds=locked_for,
                )
                return CommandOutcome(events=events, response=body, status=423)
            body = problem(401, ErrorCode.PIN_INVALID, "PIN is incorrect.")
            return CommandOutcome(events=events, response=body, status=401)

        with restaurant_context(device.restaurant_id):
            result = run_command(
                _ctx(
                    request,
                    restaurant_id=device.restaurant_id,
                    actor_role=ActorRole.SYSTEM,
                    device_id=device.id,
                ),
                handler,
            )
        response = Response(
            result.body, status=result.status, content_type="application/problem+json"
        )
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class AuthoriseView(CommandView):
    """POST /auth/authorise — manager/owner PIN → single-use authorisation token."""

    allowed_roles = tuple(STAFF_ROLES)
    input_serializer = AuthoriseInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        pin = data["pin"]
        purpose = AuthorisationPurpose(data["purpose"])
        managers = Staff.objects.filter(is_active=True, role__in=[r.value for r in MANAGER_ROLES])
        matched: Staff | None = None
        for candidate in managers:
            if verify_pin(candidate.pin_hash, pin):
                matched = candidate
                break
        if matched is None:
            raise ApiError(401, ErrorCode.PIN_INVALID, "Manager PIN is incorrect.")

        token = issue_authorisation(staff_id=matched.id, device_id=ctx.device_id, purpose=purpose)
        return CommandOutcome(
            events=[
                EventDraft(
                    AggregateType.STAFF,
                    matched.id,
                    EventType.MANAGER_AUTHORISED,
                    {
                        "purpose": purpose.value,
                        "for_device_id": str(ctx.device_id) if ctx.device_id else None,
                    },
                )
            ],
            response={
                "authorisation_token": token,
                "expires_in": settings.AUTHORISATION_TOKEN_TTL_SECONDS,
            },
        )


@method_decorator(csrf_exempt, name="dispatch")
class OwnerLoginView(CommandView):
    """POST /auth/owner/login — email + password; TOTP still required."""

    authentication_classes = [PassiveSessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request: Request, **kwargs: Any) -> Response:
        ser = OwnerLoginInput(data=request.data)
        ser.is_valid(raise_exception=True)
        email = ser.validated_data["email"].strip().lower()
        password = ser.validated_data["password"]

        # Owners use email as username (or Staff.email → linked user).
        user = authenticate(request, username=email, password=password)
        staff = find_owner_staff_by_email(email)
        if user is None and staff is not None and staff.user is not None:
            user = authenticate(request, username=staff.user.get_username(), password=password)

        if user is None:
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Invalid email or password.")

        staff = getattr(user, "staff", None) or staff
        if staff is None or staff.role != "OWNER" or not staff.is_active:
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Owner account required.")

        login(_django_request(request), user)
        # Idempotency without an event — restaurant from the owner staff row.
        result = run_command(
            _ctx(
                request,
                restaurant_id=staff.restaurant_id,
                actor_role=ActorRole.OWNER,
                actor_id=staff.id,
            ),
            lambda ctx: CommandOutcome(events=[], response={"totp_required": True}),
        )
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


@method_decorator(csrf_exempt, name="dispatch")
class OwnerTotpView(CommandView):
    """POST /auth/owner/totp — verify TOTP and mark the session OTP-verified."""

    authentication_classes = [PassiveSessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request: Request, **kwargs: Any) -> Response:
        django_request = _django_request(request)
        user = django_get_user(django_request)
        if user is None or not user.is_authenticated:
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Log in with email and password first.")
        django_request.user = user

        staff = getattr(user, "staff", None)
        if staff is None or staff.role != "OWNER":
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Owner account required.")

        ser = OwnerTotpInput(data=request.data)
        ser.is_valid(raise_exception=True)
        code = ser.validated_data["code"].strip()

        devices = TOTPDevice.objects.filter(user=user, confirmed=True)
        matched = None
        for device in devices:
            if device.verify_token(code):
                matched = device
                break
        if matched is None:
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Invalid TOTP code.")

        otp_login(django_request, matched)
        django_request.session.save()
        result = run_command(
            _ctx(
                request,
                restaurant_id=staff.restaurant_id,
                actor_role=ActorRole.OWNER,
                actor_id=staff.id,
            ),
            lambda ctx: CommandOutcome(events=[], response={"ok": True}),
        )
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class OwnerMeView(APIView):
    """GET /auth/owner/me — proves owner session + TOTP (middleware principal)."""

    authentication_classes = [OwnerSessionAuthentication]
    permission_classes = [RolePermission]
    allowed_roles = (ActorRole.OWNER,)

    def get(self, request: Request) -> Response:
        principal = current_principal(request)
        if principal.actor_id is None:
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Owner account required.")
        with restaurant_context(principal.restaurant_id):
            staff = Staff.objects.filter(id=principal.actor_id).first()
        if staff is None:
            raise ApiError(401, ErrorCode.TOKEN_INVALID, "Owner account required.")
        return Response(
            {
                "id": str(staff.id),
                "name": staff.full_name,
                "email": staff.email,
                "role": staff.role,
                "restaurant_id": str(staff.restaurant_id),
            }
        )


class LogoutView(CommandView):
    """POST /auth/logout — revoke staff jti and/or end owner session."""

    permission_classes = [AllowAny]

    def post(self, request: Request, **kwargs: Any) -> Response:
        principal = getattr(request, "principal", None)
        jti = _bearer_jti(request)
        if jti:
            revoke_jti(jti)

        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False):
            logout(_django_request(request))
        elif django_get_user(_django_request(request)).is_authenticated:
            logout(_django_request(request))

        if principal is None:
            # Still accept logout with only a bearer that we revoked, or a bare call.
            return Response({"ok": True})

        result = run_command(
            _ctx(
                request,
                restaurant_id=principal.restaurant_id,
                actor_id=principal.actor_id,
                actor_role=principal.actor_role,
                device_id=principal.device_id,
            ),
            lambda ctx: CommandOutcome(events=[], response={"ok": True}),
        )
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class GuestTokenView(CommandView):
    """POST /sessions/{id}/guest-token — waiter hands the tablet to the guest."""

    allowed_roles = (ActorRole.WAITER, ActorRole.MANAGER, ActorRole.OWNER)
    input_serializer = GuestTokenInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        session_id = kwargs["session_id"]
        session = TableSession.objects.filter(id=session_id, closed_at__isnull=True).first()
        if session is None:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Open session not found.")
        token = issue_guest_token(
            session_id=session.id, restaurant_id=ctx.restaurant_id, mode="guest"
        )
        return CommandOutcome(
            events=[],
            response={
                "token": token,
                "expires_in": settings.GUEST_TOKEN_TTL_SECONDS,
                "session_id": str(session.id),
                "mode": "guest",
            },
        )


class QrGuestSessionView(CommandView):
    """POST /guest/sessions/{qr_token} — guest phone via table QR; table must have an open session."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request: Request, **kwargs: Any) -> Response:
        table = find_table_by_qr_token(kwargs["qr_token"])
        if table is None:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Table not found.")

        with restaurant_context(table.restaurant_id):
            session = TableSession.objects.filter(table_id=table.id, closed_at__isnull=True).first()
            if session is None:
                raise ApiError(404, ErrorCode.NOT_FOUND, "No open session at this table.")

            token = issue_guest_token(
                session_id=session.id, restaurant_id=table.restaurant_id, mode="qr"
            )
            result = run_command(
                _ctx(request, restaurant_id=table.restaurant_id, actor_role=ActorRole.GUEST),
                lambda ctx: CommandOutcome(
                    events=[],
                    response={
                        "token": token,
                        "expires_in": settings.GUEST_TOKEN_TTL_SECONDS,
                        "session_id": str(session.id),
                        "table_number": table.number,
                        "mode": "qr",
                    },
                ),
            )
        response = Response(result.body, status=result.status)
        if result.replayed:
            response["Idempotent-Replayed"] = "true"
        return response


class GuestSessionDetailView(APIView):
    """GET /guest/sessions/{id} — guest may only read their own open session (404 otherwise)."""

    authentication_classes = [GuestAuthentication]
    permission_classes = [RolePermission]
    throttle_classes = [GuestThrottle]
    allowed_roles = (ActorRole.GUEST,)

    def get(self, request: Request, session_id: uuid.UUID) -> Response:
        principal = current_principal(request)
        if principal.session_id != session_id:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found.")

        session = TableSession.objects.filter(id=session_id).first()
        if session is None or session.closed_at is not None:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Not found.")

        return Response(
            {
                "id": str(session.id),
                "table_id": str(session.table_id),
                "opened_at": session.opened_at.isoformat().replace("+00:00", "Z"),
                "bill_total_pesewas": session.bill_total_pesewas,
            }
        )
