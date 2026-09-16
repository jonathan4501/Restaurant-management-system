"""Shift, payment and drawer endpoints. docs/09-api-contract.md §3 "Payments and shifts"."""

from __future__ import annotations

from typing import Any

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.principals import current_principal
from apps.core.commands import CommandContext, CommandOutcome
from apps.core.errors import ApiError, ErrorCode
from apps.core.permissions import RolePermission
from apps.core.roles import ActorRole, AuthorisationPurpose
from apps.core.views import CommandView
from apps.payments import commands as payment_commands
from apps.payments import reports
from apps.payments.models import Shift
from apps.payments.serializers import (
    CloseShiftInput,
    DrawerMovementInput,
    OpenShiftInput,
    RecordPaymentInput,
    ReopenSessionInput,
    VoidPaymentInput,
)

TILL = (ActorRole.CASHIER, ActorRole.MANAGER, ActorRole.OWNER)
STAFF = (
    ActorRole.WAITER,
    ActorRole.KITCHEN,
    ActorRole.CASHIER,
    ActorRole.MANAGER,
    ActorRole.OWNER,
)


def _shift_or_404(shift_id: Any) -> Shift:
    try:
        return Shift.objects.select_related("cashier").get(pk=shift_id)
    except Shift.DoesNotExist as err:
        raise ApiError(404, ErrorCode.NOT_FOUND, "Shift not found.") from err


class CurrentShiftView(APIView):
    """GET /shifts/current — the caller's open shift, or null so the UI shows the open-shift screen."""

    permission_classes = [RolePermission]
    allowed_roles = TILL

    @extend_schema(operation_id="shifts_current", responses={200: dict})
    def get(self, request: Request) -> Response:
        principal = current_principal(request)
        if principal.actor_id is None:
            return Response({"shift": None})
        shift = reports.current_shift_for(principal.actor_id)
        if shift is None:
            return Response({"shift": None})
        totals = payment_commands.shift_totals(shift.id, int(shift.opening_float_pesewas))
        return Response({"shift": {**reports.serialize_shift(shift), **totals}})


class OpenShiftView(CommandView):
    allowed_roles = TILL
    input_serializer = OpenShiftInput

    @extend_schema(operation_id="shifts_open", request=OpenShiftInput, responses={201: dict})
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return payment_commands.open_shift(ctx, data)


class CloseShiftView(CommandView):
    allowed_roles = TILL
    input_serializer = CloseShiftInput

    @extend_schema(operation_id="shifts_close", request=CloseShiftInput, responses={200: dict})
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return payment_commands.close_shift(ctx, kwargs["shift_id"], data)


class DrawerMovementView(CommandView):
    """Cash moving with no sale behind it. Always a manager's PIN and a reason."""

    allowed_roles = TILL
    input_serializer = DrawerMovementInput
    authorisation_purpose = AuthorisationPurpose.DRAWER_MOVEMENT

    @extend_schema(
        operation_id="shifts_movement", request=DrawerMovementInput, responses={201: dict}
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return payment_commands.record_drawer_movement(ctx, kwargs["shift_id"], data)


class ZReportView(APIView):
    permission_classes = [RolePermission]
    allowed_roles = TILL

    @extend_schema(operation_id="shifts_z_report", responses={200: dict})
    def get(self, request: Request, shift_id: Any) -> Response:
        return Response(reports.z_report(_shift_or_404(shift_id)))


class OpenBillsView(APIView):
    """GET /bills/open — the cashier's board: what is still owing, and what can be paid yet."""

    permission_classes = [RolePermission]
    allowed_roles = STAFF

    @extend_schema(operation_id="bills_open", responses={200: dict})
    def get(self, request: Request) -> Response:
        bills = reports.open_bills()
        return Response(
            {
                "bills": bills,
                "outstanding_pesewas": sum(b["balance_pesewas"] for b in bills),
            }
        )


class RecordPaymentView(CommandView):
    allowed_roles = TILL
    input_serializer = RecordPaymentInput

    @extend_schema(
        operation_id="sessions_record_payment", request=RecordPaymentInput, responses={201: dict}
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return payment_commands.record_payment(ctx, kwargs["session_id"], data)


class VoidPaymentView(CommandView):
    allowed_roles = TILL
    input_serializer = VoidPaymentInput
    authorisation_purpose = AuthorisationPurpose.PAYMENT_VOID

    @extend_schema(operation_id="payments_void", request=VoidPaymentInput, responses={200: dict})
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return payment_commands.void_payment(ctx, kwargs["payment_id"], data)


class ReopenSessionView(CommandView):
    """Reopening a settled bill is the classic leak, so it needs a manager and tells the owner."""

    allowed_roles = TILL
    input_serializer = ReopenSessionInput
    authorisation_purpose = AuthorisationPurpose.REOPEN

    @extend_schema(
        operation_id="sessions_reopen", request=ReopenSessionInput, responses={200: dict}
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return payment_commands.reopen_session(ctx, kwargs["session_id"], data)
