from __future__ import annotations

import json

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.views.decorators.http import require_GET
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.principals import (
    AuthError,
    Principal,
    current_principal,
    resolve_principal,
)
from apps.core.errors import ErrorCode, problem
from apps.core.roles import ActorRole

from . import metrics as stream_metrics
from .stream import AuthCheck, event_stream, replay_batch


def _since(request: HttpRequest) -> int | None:
    raw = request.headers.get("Last-Event-ID") or request.GET.get("since")
    if raw is None or raw == "":
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _problem(status: int, code: str, detail: str) -> HttpResponse:
    return HttpResponse(
        json.dumps(problem(status, code, detail)),
        status=status,
        content_type="application/problem+json",
    )


def _auth_check(request: HttpRequest, principal: Principal) -> AuthCheck:
    """Re-resolve the same headers: a revoked device, logged-out or expired token, or retired staff fails."""

    async def still_authorised() -> bool:
        try:
            current = await sync_to_async(resolve_principal)(request)
        except AuthError:
            return False
        return (
            current is not None
            and current.restaurant_id == principal.restaurant_id
            and current.actor_id == principal.actor_id
            and current.actor_role == principal.actor_role
        )

    return still_authorised


@require_GET
async def stream(request: HttpRequest) -> HttpResponseBase:
    """GET /api/v1/stream — text/event-stream. Staff and owner only; guests poll their own order."""
    try:
        principal = await sync_to_async(resolve_principal)(request)
    except AuthError as err:
        return _problem(401, err.code, err.detail)
    if principal is None:
        return _problem(401, ErrorCode.TOKEN_INVALID, "Authentication required.")
    if principal.actor_role == ActorRole.GUEST:
        return _problem(403, ErrorCode.ROLE_NOT_ALLOWED, "Guests do not receive the event stream.")

    response = StreamingHttpResponse(
        event_stream(
            principal.restaurant_id,
            str(principal.actor_role),
            _since(request),
            still_authorised=_auth_check(request, principal),
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


class EventsView(APIView):
    """GET /api/v1/events?since=<seq>&limit=200 — polling fallback with the same envelopes as the stream."""

    allowed_roles = (
        ActorRole.WAITER,
        ActorRole.KITCHEN,
        ActorRole.CASHIER,
        ActorRole.MANAGER,
        ActorRole.OWNER,
    )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "since", int, description="Last seq seen. Returns events with seq > since."
            ),
            OpenApiParameter(
                "limit", int, description="Max events scanned (default 200, max 1000)."
            ),
        ],
        responses={200: dict},
        summary="Poll events (SSE fallback)",
        description=(
            "`last_seq` is the highest seq scanned, including events this role may not see — always "
            "send it back as `since`. `has_more` means call again immediately."
        ),
    )
    def get(self, request: Request) -> Response:
        principal = current_principal(request)
        since = _since(request._request) or 0
        try:
            limit = min(1000, max(1, int(request.GET.get("limit", 200))))
        except ValueError:
            limit = 200
        batch = replay_batch(principal.restaurant_id, since, str(principal.actor_role), limit)
        return Response(
            {"events": batch.envelopes, "last_seq": batch.last_seq, "has_more": batch.truncated}
        )


@require_GET
def stream_probe(request: HttpRequest) -> JsonResponse:
    """Cheap liveness for the stream endpoint (does not open a stream)."""
    return JsonResponse({"ok": True})


@require_GET
def metrics(request: HttpRequest) -> HttpResponse:
    """GET /metrics — plain-text gauges. Needs `Authorization: Bearer $METRICS_TOKEN` unless DEBUG."""
    token = settings.METRICS_TOKEN
    if token:
        if request.headers.get("Authorization", "") != f"Bearer {token}":
            return HttpResponse(status=404)
    elif not settings.DEBUG:
        return HttpResponse(status=404)
    return HttpResponse(stream_metrics.render(), content_type="text/plain; version=0.0.4")
