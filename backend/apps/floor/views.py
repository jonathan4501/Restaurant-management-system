"""Floor read + session write endpoints."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.commands import CommandContext, CommandOutcome
from apps.core.errors import ApiError, ErrorCode
from apps.core.permissions import RolePermission
from apps.core.roles import ActorRole
from apps.core.views import CommandView
from apps.floor import commands as floor_commands
from apps.floor.models import Table, TableSession
from apps.orders.serializers import EmptyInput, OpenSessionInput
from apps.orders.serializers_read import serialize_bill, serialize_session, serialize_table

STAFF = (
    ActorRole.WAITER,
    ActorRole.KITCHEN,
    ActorRole.CASHIER,
    ActorRole.MANAGER,
    ActorRole.OWNER,
)
SESSION_WRITE = (ActorRole.WAITER, ActorRole.MANAGER, ActorRole.OWNER)
SESSION_CLOSE = (ActorRole.WAITER, ActorRole.CASHIER, ActorRole.MANAGER, ActorRole.OWNER)


class TablesView(APIView):
    permission_classes = [RolePermission]
    allowed_roles = STAFF

    @extend_schema(operation_id="tables_list", responses={200: list})
    def get(self, request: Request) -> Response:
        tables = Table.objects.filter(is_active=True).order_by("number")
        open_sessions = {
            s.table_id: s
            for s in TableSession.objects.filter(closed_at__isnull=True).select_related("table")
        }
        return Response([serialize_table(t, open_sessions.get(t.id)) for t in tables])


class OpenSessionView(CommandView):
    allowed_roles = SESSION_WRITE
    input_serializer = OpenSessionInput

    @extend_schema(operation_id="sessions_open", request=OpenSessionInput, responses={201: dict})
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return floor_commands.open_session(ctx, data)


class SessionDetailView(APIView):
    permission_classes = [RolePermission]
    allowed_roles = STAFF

    @extend_schema(operation_id="sessions_get", responses={200: dict})
    def get(self, request: Request, session_id: Any) -> Response:
        try:
            session = TableSession.objects.select_related("table").get(pk=session_id)
        except TableSession.DoesNotExist as err:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err
        return Response(serialize_session(session))


class SessionBillView(APIView):
    permission_classes = [RolePermission]
    allowed_roles = STAFF

    @extend_schema(operation_id="sessions_bill", responses={200: dict})
    def get(self, request: Request, session_id: Any) -> Response:
        try:
            session = TableSession.objects.select_related("table").get(pk=session_id)
        except TableSession.DoesNotExist as err:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.") from err
        return Response(serialize_bill(session))


class CloseSessionView(CommandView):
    allowed_roles = SESSION_CLOSE
    input_serializer = EmptyInput

    @extend_schema(operation_id="sessions_close", request=EmptyInput, responses={200: dict})
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return floor_commands.close_session(ctx, kwargs["session_id"])
