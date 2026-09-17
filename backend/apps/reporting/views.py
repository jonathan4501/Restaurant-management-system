"""
Owner reporting endpoints. docs/09-api-contract.md §Owner · docs/tasks/WS06-reporting.md.

Read-only: every figure comes from projections or indexed columns on order_events. Nothing here
writes an event or a projection row.
"""

from __future__ import annotations

from typing import Any

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Restaurant
from apps.accounts.principals import current_principal
from apps.core.permissions import RolePermission
from apps.core.roles import ActorRole
from apps.reporting import queries
from apps.reporting.serializers import (
    EventLogQuery,
    EventLogSerializer,
    PatternsSerializer,
    TodaySerializer,
    VarianceSerializer,
    WindowQuery,
)
from apps.reporting.windows import resolve_window

OWNER = (ActorRole.MANAGER, ActorRole.OWNER)

WINDOW_PARAMS = [
    OpenApiParameter(
        name="from",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        required=False,
        description="First business date, YYYY-MM-DD. Default: six dates before `to`.",
    ),
    OpenApiParameter(
        name="to",
        type=OpenApiTypes.DATE,
        location=OpenApiParameter.QUERY,
        required=False,
        description="Last business date, YYYY-MM-DD. Default: the current business date.",
    ),
]


def _restaurant(request: Request) -> Restaurant:
    return Restaurant.objects.get(pk=current_principal(request).restaurant_id)


def _window(request: Request, restaurant: Restaurant) -> tuple[Any, Any]:
    """Map the contract's `from`/`to` query keys onto WindowQuery, then fill defaults."""
    raw = {
        "date_from": request.query_params.get("from"),
        "date_to": request.query_params.get("to"),
    }
    ser = WindowQuery(data={k: v for k, v in raw.items() if v is not None})
    ser.is_valid(raise_exception=True)
    return resolve_window(
        restaurant,
        ser.validated_data.get("from"),
        ser.validated_data.get("to"),
    )


class VarianceView(APIView):
    """GET /reports/variance — everywhere money can leave without a sale behind it."""

    permission_classes = [RolePermission]
    allowed_roles = OWNER

    @extend_schema(
        operation_id="reports_variance",
        parameters=WINDOW_PARAMS,
        responses={200: VarianceSerializer},
        description=(
            "Voids after the kitchen acknowledged, discounts and comps by staff, reopened bills, "
            "cash variance by shift, and gaps in the ticket-number sequence."
        ),
    )
    def get(self, request: Request) -> Response:
        restaurant = _restaurant(request)
        start, end = _window(request, restaurant)
        return Response(VarianceSerializer(queries.variance(restaurant, start, end)).data)


class TodayView(APIView):
    """GET /reports/today — live figures for the current business date."""

    permission_classes = [RolePermission]
    allowed_roles = OWNER

    @extend_schema(
        operation_id="reports_today",
        responses={200: TodaySerializer},
        description=(
            "Money taken so far (gross cash through the till), covers, average bill, and open bills. "
            "Computed live — today is not rolled up until after cutover."
        ),
    )
    def get(self, request: Request) -> Response:
        return Response(TodaySerializer(queries.today(_restaurant(request))).data)


class PatternsView(APIView):
    """GET /reports/patterns — how the service lands across the day."""

    permission_classes = [RolePermission]
    allowed_roles = OWNER

    @extend_schema(
        operation_id="reports_patterns",
        parameters=WINDOW_PARAMS,
        responses={200: PatternsSerializer},
        description=(
            "Money taken by hour, payment method mix, best sellers by value (from line snapshots), "
            "and average acknowledged→ready time per station."
        ),
    )
    def get(self, request: Request) -> Response:
        restaurant = _restaurant(request)
        start, end = _window(request, restaurant)
        return Response(PatternsSerializer(queries.patterns(restaurant, start, end)).data)


class EventLogView(APIView):
    """GET /events/log — every action, newest first, cursor-paged by seq."""

    permission_classes = [RolePermission]
    allowed_roles = OWNER

    @extend_schema(
        operation_id="events_log",
        parameters=[
            OpenApiParameter(
                name="cursor",
                type=OpenApiTypes.INT64,
                location=OpenApiParameter.QUERY,
                required=False,
                description="`next_cursor` from the previous page. Pages run newest first.",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Rows per page (1–200, default 100).",
            ),
            OpenApiParameter(
                name="actor_id",
                type=OpenApiTypes.UUID,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="One event type.",
            ),
            OpenApiParameter(
                name="aggregate_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="from",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Server time, inclusive (ISO 8601).",
            ),
            OpenApiParameter(
                name="to",
                type=OpenApiTypes.DATETIME,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Server time, exclusive (ISO 8601).",
            ),
            OpenApiParameter(
                name="flagged",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Only the actions the owner is asked to look at.",
            ),
        ],
        responses={200: EventLogSerializer},
        description=(
            "The full event stream for the restaurant. `flagged` is derived from the event type "
            "(and, for voids, whether the kitchen had acknowledged) — never stored."
        ),
    )
    def get(self, request: Request) -> Response:
        raw = {
            "cursor": request.query_params.get("cursor"),
            "limit": request.query_params.get("limit"),
            "actor_id": request.query_params.get("actor_id"),
            "type": request.query_params.get("type"),
            "aggregate_type": request.query_params.get("aggregate_type"),
            "date_from": request.query_params.get("from"),
            "date_to": request.query_params.get("to"),
            "flagged": request.query_params.get("flagged"),
        }
        ser = EventLogQuery(data={k: v for k, v in raw.items() if v is not None})
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        return Response(
            EventLogSerializer(
                queries.event_log(
                    cursor=data.get("cursor"),
                    limit=data.get("limit", 100),
                    actor_id=data.get("actor_id"),
                    event_type=data.get("type"),
                    aggregate_type=data.get("aggregate_type"),
                    from_at=data.get("from"),
                    to_at=data.get("to"),
                    flagged_only=bool(data.get("flagged")),
                )
            ).data
        )
