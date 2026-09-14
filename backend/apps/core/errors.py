"""
Every error is RFC 9457 application/problem+json with a stable `code` clients switch on.
The code list is documented in docs/09-api-contract.md §2. Add here first, then there.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from django.conf import settings
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    IDEMPOTENCY_KEY_MISSING = "idempotency_key_missing"
    IDEMPOTENCY_KEY_REUSED = "idempotency_key_reused"
    IDEMPOTENCY_IN_PROGRESS = "idempotency_in_progress"
    DEVICE_UNKNOWN = "device_unknown"
    DEVICE_REVOKED = "device_revoked"
    TOKEN_INVALID = "token_invalid"
    TOKEN_EXPIRED = "token_expired"
    SESSION_CLOSED = "session_closed"
    ROLE_NOT_ALLOWED = "role_not_allowed"
    AUTHORISATION_REQUIRED = "authorisation_required"
    AUTHORISATION_INVALID = "authorisation_invalid"
    AUTHORISATION_PURPOSE_MISMATCH = "authorisation_purpose_mismatch"
    SHIFT_REQUIRED = "shift_required"
    NOT_FOUND = "not_found"
    ILLEGAL_TRANSITION = "illegal_transition"
    UNSERVED_ORDERS = "unserved_orders"
    TABLE_OCCUPIED = "table_occupied"
    SHIFT_ALREADY_OPEN = "shift_already_open"
    ITEM_UNAVAILABLE = "item_unavailable"
    ITEM_INACTIVE = "item_inactive"
    MODIFIER_INVALID = "modifier_invalid"
    REQUIRED_MODIFIER_MISSING = "required_modifier_missing"
    OVERPAYMENT = "overpayment"
    DISCOUNT_EXCEEDS_SUBTOTAL = "discount_exceeds_subtotal"
    TENDERED_INSUFFICIENT = "tendered_insufficient"
    PIN_INVALID = "pin_invalid"
    PIN_LOCKED = "pin_locked"
    THROTTLED = "throttled"
    NOT_IMPLEMENTED = "not_implemented"
    INTERNAL = "internal_error"


class ApiError(Exception):
    """Raise anywhere inside a request; becomes problem+json."""

    def __init__(
        self,
        status_code: int,
        code: ErrorCode | str,
        detail: str,
        *,
        errors: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = str(code)
        self.detail = detail
        self.errors = errors or {}
        self.extra = extra or {}

    def as_problem(self) -> dict[str, Any]:
        return problem(self.status_code, self.code, self.detail, errors=self.errors, **self.extra)


def problem(
    status_code: int, code: str, detail: str, *, errors: dict[str, Any] | None = None, **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": f"{settings.ERROR_TYPE_BASE}{code}",
        "title": code.replace("_", " ").capitalize(),
        "status": status_code,
        "code": code,
        "detail": detail,
        "errors": errors or {},
    }
    body.update(extra)
    return body


def problem_response(status_code: int, code: str, detail: str, **kwargs: Any) -> Response:
    return Response(
        problem(status_code, code, detail, **kwargs),
        status=status_code,
        content_type="application/problem+json",
    )


class IllegalTransition(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, ErrorCode.ILLEGAL_TRANSITION, detail)


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    # Imported here: rest_framework.views imports this module's settings entry while it initialises.
    from rest_framework.views import exception_handler as drf_exception_handler

    if isinstance(exc, ApiError):
        return Response(
            exc.as_problem(), status=exc.status_code, content_type="application/problem+json"
        )

    if isinstance(exc, Http404):
        return problem_response(404, ErrorCode.NOT_FOUND, "Not found.")

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        return problem_response(
            400, ErrorCode.VALIDATION_ERROR, "Request body is invalid.", errors=detail
        )

    if isinstance(exc, exceptions.Throttled):
        return problem_response(
            429,
            ErrorCode.THROTTLED,
            "Too many requests.",
            retry_after_seconds=getattr(exc, "wait", None) or 0,
        )

    if isinstance(exc, exceptions.NotAuthenticated | exceptions.AuthenticationFailed):
        code = getattr(exc, "code", None) or ErrorCode.TOKEN_INVALID
        return problem_response(401, str(code), str(exc.detail))

    if isinstance(exc, exceptions.PermissionDenied):
        code = getattr(exc, "code", None) or ErrorCode.ROLE_NOT_ALLOWED
        return problem_response(403, str(code), str(exc.detail))

    if isinstance(exc, exceptions.MethodNotAllowed | exceptions.NotFound | exceptions.ParseError):
        response = drf_exception_handler(exc, context)
        if response is not None:
            code = (
                ErrorCode.NOT_FOUND if response.status_code == 404 else ErrorCode.VALIDATION_ERROR
            )
            return problem_response(response.status_code, code, str(exc.detail))

    return drf_exception_handler(exc, context)
