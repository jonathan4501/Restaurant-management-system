"""
Print endpoints (WS12). docs/tasks/WS12-print-bridge.md.

Two audiences:

*   The cashier asks for a receipt — `POST /print/receipt`, a normal CommandView, which appends
    RECEIPT_REQUESTED and lets the stream tell the bridge to print.
*   The bridge pulls the paper — `GET /print/stream`, `/print/tickets/{order_id}` and
    `/print/receipts/{session_id}`. These are plain Django views authenticated by device token
    (see printer_auth), because the bridge has no staff JWT and therefore no DRF principal.

ESC/POS rendering lives here rather than on the Pi so that the bytes which come out of a printer
are the bytes the golden-file tests in tests/test_render.py assert on. The bridge stays a dumb,
restartable pipe: fetch bytes, queue them, push them at TCP:9100.
"""

from __future__ import annotations

import json
from typing import Any

from django.http import (
    HttpRequest,
    HttpResponse,
    StreamingHttpResponse,
)
from django.http.response import HttpResponseBase
from django.views.decorators.http import require_GET
from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.principals import AuthError
from apps.core.commands import CommandContext, CommandOutcome
from apps.core.errors import ErrorCode, problem
from apps.core.roles import ActorRole
from apps.core.tenancy import restaurant_context
from apps.core.views import CommandView
from apps.floor.models import TableSession
from apps.orders.models import Order, OrderStatus
from apps.printing import commands as printing_commands
from apps.printing import payloads, render
from apps.printing.printer_auth import PrinterPrincipal, resolve_printer
from apps.printing.serializers import RequestReceiptInput
from apps.realtime.stream import event_stream

TILL = (ActorRole.CASHIER, ActorRole.MANAGER, ActorRole.OWNER)

# An order the kitchen never saw has no ticket, and a draft has no order number yet.
TICKETABLE = (
    OrderStatus.SUBMITTED,
    OrderStatus.PREPARING,
    OrderStatus.READY,
    OrderStatus.SERVED,
    OrderStatus.CLOSED,
)


class RequestReceiptView(CommandView):
    """POST /print/receipt — record that paper was asked for, then let the bridge print it."""

    allowed_roles = TILL
    input_serializer = RequestReceiptInput

    @extend_schema(
        operation_id="print_receipt",
        request=RequestReceiptInput,
        responses={201: dict},
        summary="Request a printed sales record",
        description=(
            "Appends `RECEIPT_REQUESTED` so the print bridge produces the guest's copy. Every "
            "request is logged, and `reprint` is true when paper was already produced for this "
            "bill. The sales record carries no tax line and no fiscal reference (ADR-0005)."
        ),
    )
    def post(self, request: Request, **kwargs: Any) -> Response:
        return super().post(request, **kwargs)

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        return printing_commands.request_receipt(ctx, data)


# ------------------------------------------------------------------ bridge-facing routes


def _problem(status: int, code: str, detail: str) -> HttpResponse:
    return HttpResponse(
        json.dumps(problem(status, code, detail)),
        status=status,
        content_type="application/problem+json",
    )


def _printer_or_problem(
    request: HttpRequest,
) -> tuple[PrinterPrincipal | None, HttpResponse | None]:
    try:
        return resolve_printer(request), None
    except AuthError as err:
        status = 403 if err.code == str(ErrorCode.ROLE_NOT_ALLOWED) else 401
        return None, _problem(status, err.code, err.detail)


def _escpos(payload: bytes) -> HttpResponse:
    """ESC/POS is opaque binary; the bridge writes it to the socket without looking inside."""
    response = HttpResponse(payload, content_type="application/octet-stream")
    response["Cache-Control"] = "no-store"
    return response


def _since(request: HttpRequest) -> int | None:
    raw = request.headers.get("Last-Event-ID") or request.GET.get("since")
    if raw is None or raw == "":
        return None
    try:
        return max(0, int(raw))
    except ValueError:
        return None


@require_GET
async def printer_stream(request: HttpRequest) -> HttpResponseBase:
    """
    GET /print/stream — the bridge's event feed, filtered to ORDER + SESSION events.

    `Last-Event-ID` resumes where the bridge left off after a reconnect, which is how a ticket
    submitted while the Pi was rebooting still reaches paper.
    """
    from asgiref.sync import sync_to_async

    printer, failure = await sync_to_async(_printer_or_problem)(request)
    if failure is not None:
        return failure
    assert printer is not None

    response = StreamingHttpResponse(
        event_stream(printer.restaurant_id, printer.stream_role, _since(request)),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_GET
def ticket_bytes(request: HttpRequest, order_id: Any) -> HttpResponse:
    """GET /print/tickets/{order_id}?station=KITCHEN — the kitchen ticket as ESC/POS bytes."""
    printer, failure = _printer_or_problem(request)
    if failure is not None:
        return failure
    assert printer is not None

    station = request.GET.get("station") or None
    with restaurant_context(printer.restaurant_id):
        order = (
            Order.objects.filter(pk=order_id, status__in=TICKETABLE)
            .select_related("session", "session__table")
            .prefetch_related("items")
            .first()
        )
        if order is None:
            return _problem(404, ErrorCode.NOT_FOUND, "No printable order with that id.")
        envelope = payloads.ticket_envelope(order)
        stations = payloads.stations_on(order)

    if station is not None and station not in stations:
        return _problem(404, ErrorCode.NOT_FOUND, f"Order has no work for station {station}.")
    return _escpos(render.render_kitchen_ticket(envelope, station=station))


@require_GET
def receipt_bytes(request: HttpRequest, session_id: Any) -> HttpResponse:
    """GET /print/receipts/{session_id}?reprint=1 — the guest's sales record as ESC/POS bytes."""
    printer, failure = _printer_or_problem(request)
    if failure is not None:
        return failure
    assert printer is not None

    reprint = request.GET.get("reprint") in ("1", "true", "yes")
    with restaurant_context(printer.restaurant_id):
        session = (
            TableSession.objects.filter(pk=session_id)
            .select_related("table", "restaurant", "opened_by")
            .first()
        )
        if session is None:
            return _problem(404, ErrorCode.NOT_FOUND, "Session not found.")
        bill = payloads.receipt_payload(session, reprint=reprint)
    return _escpos(render.render_receipt(bill))


@require_GET
def printer_stations(request: HttpRequest, order_id: Any) -> HttpResponse:
    """
    GET /print/tickets/{order_id}/stations — which stations have work on this order.

    The bridge asks this so a restaurant with a grill printer and a bar printer produces one ticket
    each with only its own lines, instead of the same full ticket twice.
    """
    printer, failure = _printer_or_problem(request)
    if failure is not None:
        return failure
    assert printer is not None

    with restaurant_context(printer.restaurant_id):
        order = (
            Order.objects.filter(pk=order_id, status__in=TICKETABLE)
            .prefetch_related("items")
            .first()
        )
        if order is None:
            return _problem(404, ErrorCode.NOT_FOUND, "No printable order with that id.")
        stations = payloads.stations_on(order)
    return HttpResponse(json.dumps({"stations": stations}), content_type="application/json")
