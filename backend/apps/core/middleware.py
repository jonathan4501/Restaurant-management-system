"""
Request id + tenant context for every request.

The principal is resolved here (cheap: one device lookup, one JWT decode) so that the tenant contextvar
is set before any view or DRF authentication runs. DRF's PrincipalAuthentication then just reads
request.principal. Unauthenticated requests pass through with no context; tenant-scoped queries in
such a view will raise TenantContextMissing, which is the correct failure.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.accounts.principals import AuthError, resolve_principal

from .tenancy import reset_current_restaurant, set_current_restaurant

log = logging.getLogger("renzy.request")


class RequestContextMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        started = time.perf_counter()

        principal = None
        auth_error: AuthError | None = None
        try:
            principal = resolve_principal(request)
        except AuthError as err:
            auth_error = err
        request.principal = principal  # type: ignore[attr-defined]
        request.auth_error = auth_error  # type: ignore[attr-defined]

        token = set_current_restaurant(principal.restaurant_id if principal else None)
        try:
            response = self.get_response(request)
        finally:
            reset_current_restaurant(token)

        response["X-Request-Id"] = request_id
        log.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "restaurant_id": str(principal.restaurant_id) if principal else None,
                "actor_id": str(principal.actor_id) if principal and principal.actor_id else None,
                "device_id": (
                    str(principal.device_id) if principal and principal.device_id else None
                ),
            },
        )
        return response
