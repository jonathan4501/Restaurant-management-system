"""Staff order + KDS endpoints."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.commands import CommandContext, CommandOutcome
from apps.core.errors import ApiError, ErrorCode
from apps.core.permissions import RolePermission
from apps.core.roles import ActorRole, AuthorisationPurpose
from apps.core.views import CommandView
from apps.orders import commands as order_commands
from apps.orders.models import Order
from apps.orders.serializers import (
    AddItemInput,
    CompInput,
    DiscountInput,
    EmptyInput,
    ModifyItemInput,
    OpenOrderInput,
    PriceOverrideInput,
    VoidInput,
)
from apps.orders.serializers_read import kds_tickets, serialize_order
from apps.orders.state_machine import OrderCommand, transition

ORDER_WRITE = (ActorRole.WAITER, ActorRole.MANAGER, ActorRole.OWNER)
ORDER_READ = (
    ActorRole.WAITER,
    ActorRole.KITCHEN,
    ActorRole.CASHIER,
    ActorRole.MANAGER,
    ActorRole.OWNER,
)
KITCHEN = (ActorRole.KITCHEN, ActorRole.MANAGER, ActorRole.OWNER)
SERVE = (ActorRole.WAITER, ActorRole.KITCHEN, ActorRole.MANAGER, ActorRole.OWNER)
VOID = (ActorRole.WAITER, ActorRole.CASHIER, ActorRole.MANAGER, ActorRole.OWNER)
DISCOUNT = (ActorRole.CASHIER, ActorRole.MANAGER, ActorRole.OWNER)
COMP = (ActorRole.MANAGER, ActorRole.OWNER)


class OpenOrderView(CommandView):
    allowed_roles = ORDER_WRITE
    input_serializer = OpenOrderInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.open_order(ctx, data)


class OrderDetailView(APIView):
    permission_classes = [RolePermission]
    allowed_roles = ORDER_READ

    def get(self, request: Request, order_id: Any) -> Response:
        try:
            order = Order.objects.select_related("session", "session__table").get(pk=order_id)
        except Order.DoesNotExist as err:
            raise ApiError(404, ErrorCode.NOT_FOUND, "Order not found.") from err
        return Response(serialize_order(order))


class AddItemView(CommandView):
    allowed_roles = ORDER_WRITE
    input_serializer = AddItemInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.add_item(ctx, kwargs["order_id"], data)


class RemoveItemView(CommandView):
    allowed_roles = ORDER_WRITE
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.remove_item(ctx, kwargs["order_id"], kwargs["item_id"])


class ModifyItemView(CommandView):
    allowed_roles = ORDER_WRITE
    input_serializer = ModifyItemInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.modify_item(ctx, kwargs["order_id"], kwargs["item_id"], data)


class SubmitOrderView(CommandView):
    allowed_roles = ORDER_WRITE
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.submit_order(ctx, kwargs["order_id"])


class AckOrderView(CommandView):
    allowed_roles = KITCHEN
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.ack_order(ctx, kwargs["order_id"])


class StartItemView(CommandView):
    allowed_roles = (ActorRole.KITCHEN,)
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.start_item(ctx, kwargs["order_id"], kwargs["item_id"])


class ReadyItemView(CommandView):
    allowed_roles = (ActorRole.KITCHEN,)
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.ready_item(ctx, kwargs["order_id"], kwargs["item_id"])


class ReadyOrderView(CommandView):
    allowed_roles = KITCHEN
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.ready_order(ctx, kwargs["order_id"])


class ServeOrderView(CommandView):
    allowed_roles = SERVE
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.serve_order(ctx, kwargs["order_id"])


class VoidOrderView(CommandView):
    allowed_roles = VOID
    input_serializer = VoidInput

    def needs_authorisation(
        self, data: dict[str, Any], **kwargs: Any
    ) -> AuthorisationPurpose | None:
        try:
            order = Order.objects.get(pk=kwargs["order_id"])
        except Order.DoesNotExist:
            return None
        try:
            t = transition(order.status, OrderCommand.VOID)
        except Exception:
            return None
        return t.authorisation

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.void_order(ctx, kwargs["order_id"], data)


class DiscountView(CommandView):
    allowed_roles = DISCOUNT
    input_serializer = DiscountInput
    authorisation_purpose = AuthorisationPurpose.DISCOUNT

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.apply_discount(ctx, kwargs["order_id"], data)


class CompView(CommandView):
    allowed_roles = COMP
    input_serializer = CompInput
    authorisation_purpose = AuthorisationPurpose.COMP

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.apply_comp(ctx, kwargs["order_id"], data)


class PriceOverrideView(CommandView):
    allowed_roles = COMP
    input_serializer = PriceOverrideInput
    authorisation_purpose = AuthorisationPurpose.PRICE_OVERRIDE

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return order_commands.price_override(ctx, kwargs["order_id"], kwargs["item_id"], data)


class FireView(CommandView):
    """Phase 4 — registered so the route exists; returns 501."""

    allowed_roles = ORDER_WRITE
    input_serializer = EmptyInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        raise ApiError(501, ErrorCode.NOT_IMPLEMENTED, "Course firing is Phase 4.")


class KdsTicketsView(APIView):
    permission_classes = [RolePermission]
    allowed_roles = KITCHEN

    @extend_schema(
        operation_id="kds_tickets",
        parameters=[
            OpenApiParameter(
                "station",
                str,
                description="Show only lines for one prep station: KITCHEN, GRILL or BAR.",
                enum=["KITCHEN", "GRILL", "BAR"],
            )
        ],
        responses={200: list},
    )
    def get(self, request: Request) -> Response:
        station = request.query_params.get("station")
        return Response(kds_tickets(station=station))
