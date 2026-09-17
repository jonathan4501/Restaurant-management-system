"""
The print endpoints against the real database: payload builders, the RECEIPT_REQUESTED command,
and the device-token routes the Pi bridge uses.
"""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.authorisation import issue_authorisation
from apps.accounts.models import Staff
from apps.core.roles import AggregateType, AuthorisationPurpose
from apps.core.tenancy import restaurant_context
from apps.core.uuid7 import uuid7
from apps.floor.models import Table, TableSession
from apps.orders.events import EventType
from apps.orders.models import Order, OrderEvent
from apps.printing import payloads
from apps.printing.render import render_kitchen_ticket, render_receipt

from .conftest import (
    headers,
    open_session,
    open_shift,
    pay,
    printer_headers,
    serve_round,
)

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ payload builders


def test_ticket_envelope_matches_the_stream_shape(
    api, waiter_auth, kitchen_auth, table, jollof, beer
):
    """render_kitchen_ticket() has one input format whether the ticket came live or was rebuilt."""
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 2), (beer, 3)])

    order = Order.objects.select_related("session", "session__table").get(pk=order_id)
    envelope = payloads.ticket_envelope(order)

    assert envelope["type"] == "ORDER_SUBMITTED"
    assert envelope["payload"]["table_number"] == "7"
    assert envelope["payload"]["order_number"] == order.order_number
    names = [line["name"] for line in envelope["payload"]["lines"]]
    assert "Jollof Rice with Grilled Chicken" in names
    assert "Club Beer" in names
    # Renders without raising: the shape is the one the renderer expects.
    assert render_kitchen_ticket(envelope).startswith(b"\x1b")


def test_ticket_envelope_uses_the_server_timestamp(api, waiter_auth, kitchen_auth, table, jollof):
    """Invariant 6: the paper shows when the server accepted the order, not the tablet's clock."""
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])

    order = Order.objects.select_related("session", "session__table").get(pk=order_id)
    envelope = payloads.ticket_envelope(order)
    assert envelope["created_at"] == order.submitted_at.isoformat().replace("+00:00", "Z")


def test_stations_on_an_order(api, waiter_auth, kitchen_auth, table, jollof, beer):
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1), (beer, 2)])
    order = Order.objects.prefetch_related("items").get(pk=order_id)
    assert payloads.stations_on(order) == ["BAR", "KITCHEN"]


def test_receipt_payload_money_is_integer_pesewas(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof, beer
):
    """2 x 7500 + 3 x 1500 = 19500. Every money field is an int, never a float (invariant 1)."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 2), (beer, 3)])
    open_shift(api, cashier_auth)
    assert (
        pay(api, cashier_auth, session_id, "CASH", 19500, tendered_pesewas=20000).status_code == 201
    )

    session = TableSession.objects.select_related("table", "restaurant", "opened_by").get(
        pk=session_id
    )
    bill = payloads.receipt_payload(session)

    assert bill["total_pesewas"] == 19500
    assert bill["subtotal_pesewas"] == 19500
    assert bill["paid_pesewas"] == 19500
    assert bill["balance_pesewas"] == 0
    assert bill["change_pesewas"] == 500
    for field in (
        "subtotal_pesewas",
        "total_pesewas",
        "paid_pesewas",
        "balance_pesewas",
        "change_pesewas",
    ):
        assert isinstance(bill[field], int), f"{field} must be int pesewas, got {type(bill[field])}"
    for line in bill["lines"]:
        assert isinstance(line["line_total_pesewas"], int)
        assert isinstance(line["unit_price_pesewas"], int)


def test_receipt_payload_has_no_tax_fields(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof
):
    """ADR-0005. If a tax key ever appears here it would reach paper."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    session = TableSession.objects.select_related("table", "restaurant", "opened_by").get(
        pk=session_id
    )
    bill = payloads.receipt_payload(session)

    keys = " ".join(bill).upper()
    for forbidden in ("VAT", "TAX", "NHIL", "GETFUND", "LEVY", "FISCAL", "IRN", "GRA"):
        assert forbidden not in keys


def test_receipt_payload_uses_snapshots_not_the_live_menu_price(
    api, waiter_auth, kitchen_auth, table, jollof
):
    """Invariant 2: tomorrow's price must not rewrite yesterday's bill."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])

    jollof.price_pesewas = 999900
    jollof.save(update_fields=["price_pesewas"])

    session = TableSession.objects.select_related("table", "restaurant", "opened_by").get(
        pk=session_id
    )
    bill = payloads.receipt_payload(session)
    assert bill["lines"][0]["unit_price_pesewas"] == 7500
    assert bill["total_pesewas"] == 7500


def test_receipt_payload_excludes_voided_payments(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof, manager
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    open_shift(api, cashier_auth)
    payment = pay(api, cashier_auth, session_id, "CASH", 7500, tendered_pesewas=7500)
    assert payment.status_code == 201

    _, _, _, dev = cashier_auth
    token = issue_authorisation(
        staff_id=manager.id, device_id=dev.id, purpose=AuthorisationPurpose.PAYMENT_VOID
    )
    void = api.post(
        f"/api/v1/payments/{payment.data['id']}/void",
        {"authorisation": {"token": token, "reason_code": "MISKEY"}},
        format="json",
        **headers(cashier_auth),
    )
    assert void.status_code == 200, void.data

    session = TableSession.objects.select_related("table", "restaurant", "opened_by").get(
        pk=session_id
    )
    bill = payloads.receipt_payload(session)
    assert bill["payments"] == []
    assert bill["paid_pesewas"] == 0
    assert bill["balance_pesewas"] == 7500


# ------------------------------------------------------------------ POST /print/receipt


def test_requesting_a_receipt_appends_receipt_requested(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])

    response = api.post(
        "/api/v1/print/receipt",
        {"session_id": session_id},
        format="json",
        **headers(cashier_auth),
    )
    assert response.status_code == 201, response.data
    assert response.data["reprint"] is False
    assert response.data["table_number"] == "7"

    event = OrderEvent.objects.get(event_type=EventType.RECEIPT_REQUESTED)
    assert event.aggregate_type == str(AggregateType.SESSION)
    assert str(event.aggregate_id) == session_id
    assert event.payload == {"table_number": "7", "reprint": False}
    # The actor and the device are on the event: that is the audit trail for a reprint.
    assert event.actor_id is not None
    assert event.device_id is not None


def test_a_second_request_is_recorded_as_a_reprint(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof
):
    """Fraud pattern 5: a reprint reused to legitimise an unrecorded sale. It must be visible."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])

    first = api.post(
        "/api/v1/print/receipt", {"session_id": session_id}, format="json", **headers(cashier_auth)
    )
    second = api.post(
        "/api/v1/print/receipt", {"session_id": session_id}, format="json", **headers(cashier_auth)
    )
    assert first.data["reprint"] is False
    assert second.data["reprint"] is True
    assert OrderEvent.objects.filter(event_type=EventType.RECEIPT_REQUESTED).count() == 2


def test_requesting_a_receipt_is_idempotent(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof
):
    """Invariant 5: a cashier double-tapping Print must not append two events."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])

    key = str(uuid7())
    body = {"session_id": session_id}
    first = api.post("/api/v1/print/receipt", body, format="json", **headers(cashier_auth, key))
    second = api.post("/api/v1/print/receipt", body, format="json", **headers(cashier_auth, key))

    assert first.status_code == 201
    assert second.status_code == 201
    assert second["Idempotent-Replayed"] == "true"
    assert second.data["reprint"] is False, "a replay must return the original answer"
    assert OrderEvent.objects.filter(event_type=EventType.RECEIPT_REQUESTED).count() == 1


def test_a_waiter_may_not_request_a_receipt(api, waiter_auth, table):
    open_session(api, waiter_auth, table)
    session = TableSession.objects.get()
    response = api.post(
        "/api/v1/print/receipt",
        {"session_id": str(session.id)},
        format="json",
        **headers(waiter_auth),
    )
    assert response.status_code == 403


def test_requesting_a_receipt_for_an_unknown_bill_is_404(api, cashier_auth):
    response = api.post(
        "/api/v1/print/receipt",
        {"session_id": str(uuid7())},
        format="json",
        **headers(cashier_auth),
    )
    assert response.status_code == 404


# ------------------------------------------------------------------ bridge-facing routes


def test_bridge_fetches_ticket_bytes(
    api, waiter_auth, kitchen_auth, table, jollof, beer, printer_device
):
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 2), (beer, 3)])

    response = api.get(f"/api/v1/print/tickets/{order_id}", **printer_headers(printer_device))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/octet-stream"
    body = response.content
    assert body.endswith(b"\x1dVA\x00") or b"\x1dV" in body  # ESC/POS cut
    text = body.decode("cp437", errors="replace")
    assert "Table 7" in text
    assert "Jollof Rice with Grilled Chicken" in text


def test_bridge_fetches_one_station_at_a_time(
    api, waiter_auth, kitchen_auth, table, jollof, beer, printer_device
):
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1), (beer, 2)])

    bar = api.get(
        f"/api/v1/print/tickets/{order_id}?station=BAR", **printer_headers(printer_device)
    )
    assert bar.status_code == 200
    text = bar.content.decode("cp437", errors="replace")
    assert "Club Beer" in text
    assert "Jollof" not in text

    stations = api.get(
        f"/api/v1/print/tickets/{order_id}/stations", **printer_headers(printer_device)
    )
    assert stations.status_code == 200
    assert stations.json() == {"stations": ["BAR", "KITCHEN"]}


def test_bridge_asking_for_a_station_with_no_work_is_404(
    api, waiter_auth, kitchen_auth, table, jollof, printer_device
):
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    response = api.get(
        f"/api/v1/print/tickets/{order_id}?station=BAR", **printer_headers(printer_device)
    )
    assert response.status_code == 404


def test_bridge_fetches_receipt_bytes(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof, printer_device
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    open_shift(api, cashier_auth)
    assert (
        pay(api, cashier_auth, session_id, "CASH", 7500, tendered_pesewas=10000).status_code == 201
    )

    response = api.get(f"/api/v1/print/receipts/{session_id}", **printer_headers(printer_device))
    assert response.status_code == 200
    text = response.content.decode("cp437", errors="replace")
    assert "SALES RECORD" in text
    assert "75.00" in text
    assert "Change" in text
    assert "REPRINT" not in text

    reprint = api.get(
        f"/api/v1/print/receipts/{session_id}?reprint=1", **printer_headers(printer_device)
    )
    assert "* REPRINT *" in reprint.content.decode("cp437", errors="replace")


def test_a_draft_order_has_no_ticket(api, waiter_auth, table, jollof, printer_device):
    """Nothing was sent to the kitchen, so there is nothing to print."""
    session_id = open_session(api, waiter_auth, table)
    order_id = str(uuid7())
    api.post(
        "/api/v1/orders",
        {"id": order_id, "session_id": session_id},
        format="json",
        **headers(waiter_auth),
    )
    response = api.get(f"/api/v1/print/tickets/{order_id}", **printer_headers(printer_device))
    assert response.status_code == 404


# ------------------------------------------------------------------ printer auth


def test_printer_routes_need_a_device_token(api, waiter_auth, kitchen_auth, table, jollof):
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    response = api.get(f"/api/v1/print/tickets/{order_id}")
    assert response.status_code == 401


def test_a_tablet_may_not_pull_printable_bytes(
    api, waiter_auth, kitchen_auth, table, jollof, till_device
):
    """A waiter's tablet is not a printer: without PRINTER in allowed_roles it is refused."""
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    _, token = till_device
    response = api.get(f"/api/v1/print/tickets/{order_id}", HTTP_X_DEVICE_TOKEN=token)
    assert response.status_code == 403


def test_a_revoked_pi_is_refused(api, waiter_auth, kitchen_auth, table, jollof, printer_device):
    session_id = open_session(api, waiter_auth, table)
    order_id = serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    dev, token = printer_device
    dev.revoked_at = timezone.now()
    dev.save(update_fields=["revoked_at"])

    response = api.get(f"/api/v1/print/tickets/{order_id}", HTTP_X_DEVICE_TOKEN=token)
    assert response.status_code == 401


def test_a_pi_cannot_read_another_restaurants_bill(
    api, waiter_auth, kitchen_auth, table, jollof, printer_device, other_restaurant
):
    """Invariant 7: the printer token is scoped to its own restaurant."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])

    with restaurant_context(other_restaurant.id):
        other_staff = Staff.objects.create(
            restaurant_id=other_restaurant.id, full_name="Someone", role="WAITER", pin_hash="x"
        )
        other_table = Table.objects.create(
            restaurant_id=other_restaurant.id, number="1", qr_token=Table.new_qr_token()
        )
        other_session = TableSession.objects.create(
            restaurant_id=other_restaurant.id,
            table=other_table,
            opened_by=other_staff,
            opened_at=timezone.now(),
        )

    response = api.get(
        f"/api/v1/print/receipts/{other_session.id}", **printer_headers(printer_device)
    )
    assert response.status_code == 404


def test_receipt_bytes_match_the_pure_renderer(
    api, waiter_auth, kitchen_auth, cashier_auth, table, jollof, printer_device
):
    """The endpoint is the renderer plus a payload builder — no second code path to paper."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, [(jollof, 1)])
    open_shift(api, cashier_auth)
    pay(api, cashier_auth, session_id, "CASH", 7500, tendered_pesewas=7500)

    over_http = api.get(
        f"/api/v1/print/receipts/{session_id}", **printer_headers(printer_device)
    ).content

    session = TableSession.objects.select_related("table", "restaurant", "opened_by").get(
        pk=session_id
    )
    bill = payloads.receipt_payload(session)
    # printed_at is a clock read, and is not printed on the receipt; everything else must match.
    assert over_http == render_receipt(bill)
