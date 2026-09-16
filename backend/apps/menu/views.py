"""GET /menu (ETag + Redis cache) and menu write commands."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.principals import GuestAuthentication, current_principal
from apps.accounts.throttles import GuestThrottle
from apps.core.commands import CommandContext, CommandOutcome
from apps.core.permissions import RolePermission
from apps.core.roles import STAFF_ROLES, ActorRole, AuthorisationPurpose
from apps.core.views import CommandView
from apps.menu import commands as menu_commands
from apps.menu.cache import compute_etag, get_cached_menu, quote_etag, set_cached_menu
from apps.menu.serializers import build_menu_payload

MENU_READ_ROLES = tuple(STAFF_ROLES) + (ActorRole.GUEST,)
MENU_86_ROLES = (ActorRole.KITCHEN, ActorRole.MANAGER, ActorRole.OWNER)
MENU_PRICE_ROLES = (ActorRole.MANAGER, ActorRole.OWNER)


class MenuView(APIView):
    """GET /menu — full active menu tree with ETag / If-None-Match."""

    permission_classes = [RolePermission]
    allowed_roles = MENU_READ_ROLES

    @extend_schema(
        operation_id="menu_get",
        summary="Full menu (categories → items → modifier groups → modifiers)",
        responses={200: dict, 304: None},
    )
    def get(self, request: Request) -> Response:
        principal = current_principal(request)
        cached = get_cached_menu(principal.restaurant_id)
        if cached is not None:
            body, etag = cached
        else:
            body = build_menu_payload()
            etag = compute_etag(body)
            set_cached_menu(principal.restaurant_id, body, etag)

        quoted = quote_etag(etag)
        if_none = request.headers.get("If-None-Match")
        if if_none is not None and etag in if_none:
            return Response(status=304, headers={"ETag": quoted})

        response = Response(body)
        response["ETag"] = quoted
        response["Cache-Control"] = "private, must-revalidate"
        return response


class GuestMenuView(MenuView):
    """GET /guest/menu — the same menu on the sandboxed guest router (guest token only, throttled)."""

    authentication_classes = [GuestAuthentication]
    throttle_classes = [GuestThrottle]
    allowed_roles = (ActorRole.GUEST,)

    @extend_schema(
        operation_id="guest_menu_get",
        summary="Full menu for a guest token",
        responses={200: dict, 304: None},
    )
    def get(self, request: Request) -> Response:
        return super().get(request)


class EightySixView(CommandView):
    allowed_roles = MENU_86_ROLES

    @extend_schema(
        operation_id="menu_item_86",
        summary="86 a menu item (mark unavailable)",
        request=None,
        responses={200: dict},
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return menu_commands.eighty_six(ctx, kwargs["item_id"])


class RestoreView(CommandView):
    allowed_roles = MENU_86_ROLES

    @extend_schema(
        operation_id="menu_item_restore",
        summary="Restore an 86'd menu item",
        request=None,
        responses={200: dict},
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return menu_commands.restore(ctx, kwargs["item_id"])


class PriceChangeInput(serializers.Serializer):
    price_pesewas = serializers.IntegerField(min_value=0)


class PriceChangeView(CommandView):
    """
    POST /menu/items/{id}/price.

    During service hours, requires manager authorisation with purpose
    PRICE_CHANGE_IN_SERVICE. Outside service hours, no authorisation block.
    """

    allowed_roles = MENU_PRICE_ROLES
    input_serializer = PriceChangeInput

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        super().initial(request, *args, **kwargs)
        principal = current_principal(request)
        self._during_service = menu_commands.price_change_during_service(principal.restaurant_id)

    def needs_authorisation(
        self, data: dict[str, Any], **kwargs: Any
    ) -> AuthorisationPurpose | None:
        if getattr(self, "_during_service", True):
            return AuthorisationPurpose.PRICE_CHANGE_IN_SERVICE
        return None

    @extend_schema(
        operation_id="menu_item_price",
        summary="Change a menu item price (auth required during service)",
        request=PriceChangeInput,
        responses={200: dict},
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return menu_commands.change_price(
            ctx,
            kwargs["item_id"],
            data["price_pesewas"],
            during_service=getattr(self, "_during_service", True),
        )
