"""Guest sandboxed order routes. Hostile input — every lookup filtered by principal.session_id."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.principals import GuestAuthentication, current_principal
from apps.accounts.throttles import GuestThrottle
from apps.accounts.tokens import decode
from apps.core.commands import CommandContext, CommandOutcome
from apps.core.errors import ApiError, ErrorCode
from apps.core.permissions import RolePermission
from apps.core.roles import ActorRole
from apps.core.views import CommandView
from apps.orders import commands as order_commands
from apps.orders.models import Order, OrderOrigin
from apps.orders.serializers import AddItemInput, EmptyInput, ModifyItemInput, OpenOrderInput
from apps.orders.serializers_read import serialize_order


def _guest_origin(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return OrderOrigin.GUEST_TABLET
    try:
        claims = decode(token.strip())
    except Exception:
        return OrderOrigin.GUEST_TABLET
    return OrderOrigin.GUEST_QR if claims.get("mode") == "qr" else OrderOrigin.GUEST_TABLET


def _own_order(principal, order_id: uuid.UUID) -> Order:
    try:
        order = Order.objects.select_related("session", "session__table").get(pk=order_id)
    except Order.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order not found.") from err
    if principal.session_id is None or order.session_id != principal.session_id:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Order not found.")
    return order


class GuestCommandView(CommandView):
    authentication_classes = [GuestAuthentication]
    permission_classes = [RolePermission]
    throttle_classes = [GuestThrottle]
    allowed_roles = (ActorRole.GUEST,)


class GuestOpenOrderView(GuestCommandView):
    input_serializer = OpenOrderInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        principal = current_principal(self.request)
        if data["session_id"] != principal.session_id:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Session not found.")
        origin = _guest_origin(self.request)
        return order_commands.open_order(ctx, data, origin=origin)


class GuestAddItemView(GuestCommandView):
    input_serializer = AddItemInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        _own_order(current_principal(self.request), kwargs["order_id"])
        return order_commands.add_item(ctx, kwargs["order_id"], data)


class GuestRemoveItemView(GuestCommandView):
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        _own_order(current_principal(self.request), kwargs["order_id"])
        return order_commands.remove_item(ctx, kwargs["order_id"], kwargs["item_id"])


class GuestModifyItemView(GuestCommandView):
    input_serializer = ModifyItemInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        _own_order(current_principal(self.request), kwargs["order_id"])
        return order_commands.modify_item(ctx, kwargs["order_id"], kwargs["item_id"], data)


class GuestSubmitOrderView(GuestCommandView):
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        _own_order(current_principal(self.request), kwargs["order_id"])
        return order_commands.submit_order(ctx, kwargs["order_id"])


class GuestOrderDetailView(APIView):
    authentication_classes = [GuestAuthentication]
    permission_classes = [RolePermission]
    throttle_classes = [GuestThrottle]
    allowed_roles = (ActorRole.GUEST,)

    def get(self, request: Request, order_id: uuid.UUID) -> Response:
        order = _own_order(current_principal(request), order_id)
        return Response(serialize_order(order))
