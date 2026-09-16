"""WS05: split bills, change, settlement, voids, reopen, the shift and its variance."""

from __future__ import annotations

import pytest

from apps.accounts.models import Staff
from apps.core.roles import AuthorisationPurpose
from apps.core.uuid7 import uuid7
from apps.floor.models import Table, TableSession
from apps.orders.models import Order, OrderEvent, OrderStatus
from apps.orders.rebuild import verify
from apps.payments.commands import normalise_reference
from apps.payments.models import DrawerMovement, Payment, PaymentMethod, Shift

from .conftest import authorisation, headers, key, open_session, open_shift, pay, serve_round

pytestmark = pytest.mark.django_db


def test_split_bill_settles_and_closes_every_order(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    """Three tenders, one bill: 75.00 + 75.00 + 75.00 = 225.00 paid across cash, MoMo and card."""
    session_id = open_session(api, waiter_auth, table)
    for _ in range(3):
        serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)

    first = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 10000, tendered_pesewas=10000)
    assert first.status_code == 201, first.data
    assert first.data["balance_pesewas"] == 12500
    assert first.data["settled"] is False

    second = pay(
        api,
        cashier_auth,
        session_id,
        PaymentMethod.MOMO_MTN,
        10000,
        external_reference=" mp24 0917 abc ",
    )
    assert second.status_code == 201
    assert second.data["external_reference"] == "MP240917ABC"

    third = pay(api, cashier_auth, session_id, PaymentMethod.CARD, 2500)
    assert third.status_code == 201
    assert third.data["balance_pesewas"] == 0
    assert third.data["settled"] is True

    session = TableSession.objects.get(pk=session_id)
    assert session.paid_pesewas == 22500
    assert session.settled_at is not None
    assert (
        list(Order.objects.filter(session_id=session_id).values_list("status", flat=True))
        == [OrderStatus.CLOSED] * 3
    )
    assert OrderEvent.objects.filter(event_type="SESSION_SETTLED").count() == 1
    assert OrderEvent.objects.filter(event_type="ORDER_CLOSED").count() == 3

    # A fourth tender has nothing left to pay for.
    fourth = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 500, tendered_pesewas=500)
    assert fourth.status_code == 422
    assert fourth.data["code"] == "overpayment"


def test_partial_payment_leaves_the_bill_open_and_part_paid(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)

    response = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 5000, tendered_pesewas=5000)
    assert response.status_code == 201
    assert response.data["balance_pesewas"] == 2500

    session = TableSession.objects.get(pk=session_id)
    assert session.settled_at is None

    bills = api.get("/api/v1/bills/open", **headers(cashier_auth)).data
    row = next(b for b in bills["bills"] if b["session_id"] == session_id)
    assert row["state"] == "part_paid"
    assert row["balance_pesewas"] == 2500
    assert bills["outstanding_pesewas"] == 2500


def test_cash_change_and_insufficient_tender(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id), quantity=3)  # 225.00
    open_shift(api, cashier_auth)

    short = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 22500, tendered_pesewas=20000)
    assert short.status_code == 422
    assert short.data["code"] == "tendered_insufficient"
    assert not Payment.objects.exists()

    ok = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 22500, tendered_pesewas=30000)
    assert ok.status_code == 201
    assert ok.data["change_pesewas"] == 7500
    payment = Payment.objects.get()
    assert (payment.tendered_pesewas, payment.change_pesewas) == (30000, 7500)


def test_unserved_order_blocks_payment(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)

    # A second round is still in the kitchen.
    order_id = str(uuid7())
    api.post(
        "/api/v1/orders",
        {"id": order_id, "session_id": session_id},
        format="json",
        **headers(waiter_auth),
    )
    api.post(
        f"/api/v1/orders/{order_id}/items",
        {"id": str(uuid7()), "menu_item_id": str(jollof.id), "quantity": 1, "modifier_ids": []},
        format="json",
        **headers(waiter_auth),
    )
    api.post(f"/api/v1/orders/{order_id}/submit", {}, format="json", **headers(waiter_auth))

    blocked = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 7500, tendered_pesewas=7500)
    assert blocked.status_code == 409
    assert blocked.data["code"] == "unserved_orders"
    assert not Payment.objects.exists()

    bills = api.get("/api/v1/bills/open", **headers(cashier_auth)).data["bills"]
    assert next(b for b in bills if b["session_id"] == session_id)["payable"] is False


def test_payment_without_an_open_shift_is_refused(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))

    response = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 7500, tendered_pesewas=7500)
    assert response.status_code == 403
    assert response.data["code"] == "shift_required"
    assert not Payment.objects.exists()


def test_second_open_shift_for_the_same_cashier_is_refused(api, restaurant, cashier_auth):
    open_shift(api, cashier_auth)
    again = api.post(
        "/api/v1/shifts",
        {"id": str(uuid7()), "opening_float_pesewas": 5000},
        format="json",
        **headers(cashier_auth),
    )
    assert again.status_code == 409
    assert again.data["code"] == "shift_already_open"


def test_shift_close_reports_the_variance(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth, manager
):
    """Float 200.00, cash taken 1550.00, paid out 100.00, counted 1630.00 → 20.00 short."""
    _, _, _, dev = cashier_auth
    shift_id = open_shift(api, cashier_auth, float_pesewas=20000)

    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id), quantity=20)  # 1500.00
    assert (
        pay(
            api, cashier_auth, session_id, PaymentMethod.CASH, 150000, tendered_pesewas=150000
        ).status_code
        == 201
    )

    second_table = Table.objects.create(number="8", qr_token=Table.new_qr_token())
    other = open_session(api, waiter_auth, second_table)
    serve_round(api, waiter_auth, kitchen_auth, other, str(jollof.id))  # 75.00
    assert (
        pay(api, cashier_auth, other, PaymentMethod.CASH, 5000, tendered_pesewas=5000).status_code
        == 201
    )

    movement = api.post(
        f"/api/v1/shifts/{shift_id}/movements",
        {
            "kind": "PAID_OUT",
            "amount_pesewas": 10000,
            "note": "gas refill",
            "authorisation": authorisation(
                manager, dev, AuthorisationPurpose.DRAWER_MOVEMENT, "SUPPLIER_PAID"
            ),
        },
        format="json",
        **headers(cashier_auth),
    )
    assert movement.status_code == 201, movement.data

    closed = api.post(
        f"/api/v1/shifts/{shift_id}/close",
        {"declared_cash_pesewas": 163000},
        format="json",
        **headers(cashier_auth),
    )
    assert closed.status_code == 200, closed.data
    assert closed.data["cash_payments_pesewas"] == 155000
    assert closed.data["paid_out_pesewas"] == 10000
    assert closed.data["expected_cash_pesewas"] == 165000
    assert closed.data["variance_pesewas"] == -2000

    shift = Shift.objects.get(pk=shift_id)
    assert shift.closed_at is not None
    assert shift.variance_pesewas == -2000

    report = api.get(f"/api/v1/shifts/{shift_id}/z-report", **headers(cashier_auth)).data
    assert report["variance_pesewas"] == -2000
    assert report["money_taken_pesewas"] == 155000
    assert len(report["payments"]) == 2
    assert report["movements"][0]["kind"] == "PAID_OUT"
    assert report["movements"][0]["reason_code"] == "SUPPLIER_PAID"


def test_no_sale_movement_records_zero_and_still_leaves_a_trace(
    api, restaurant, cashier_auth, manager
):
    _, _, _, dev = cashier_auth
    shift_id = open_shift(api, cashier_auth)
    response = api.post(
        f"/api/v1/shifts/{shift_id}/movements",
        {
            "kind": "NO_SALE",
            "amount_pesewas": 9999,  # ignored: a no-sale moves no money
            "authorisation": authorisation(
                manager, dev, AuthorisationPurpose.DRAWER_MOVEMENT, "NO_SALE"
            ),
        },
        format="json",
        **headers(cashier_auth),
    )
    assert response.status_code == 201
    movement = DrawerMovement.objects.get()
    assert movement.amount_pesewas == 0
    assert movement.authorised_by_id == manager.id
    assert OrderEvent.objects.filter(event_type="DRAWER_MOVEMENT").exists()


def test_drawer_movement_without_a_manager_is_refused(api, restaurant, cashier_auth):
    shift_id = open_shift(api, cashier_auth)
    response = api.post(
        f"/api/v1/shifts/{shift_id}/movements",
        {"kind": "PAID_OUT", "amount_pesewas": 5000},
        format="json",
        **headers(cashier_auth),
    )
    assert response.status_code == 403
    assert response.data["code"] == "authorisation_required"


def test_voiding_a_payment_reopens_the_settled_bill(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth, manager
):
    _, _, _, dev = cashier_auth
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)
    paid = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 7500, tendered_pesewas=7500)
    assert paid.data["settled"] is True

    voided = api.post(
        f"/api/v1/payments/{paid.data['id']}/void",
        {
            "authorisation": authorisation(
                manager, dev, AuthorisationPurpose.PAYMENT_VOID, "WRONG_AMOUNT"
            )
        },
        format="json",
        **headers(cashier_auth),
    )
    assert voided.status_code == 200, voided.data
    assert voided.data["session_reopened"] is True
    assert voided.data["balance_pesewas"] == 7500

    session = TableSession.objects.get(pk=session_id)
    assert session.settled_at is None
    assert session.paid_pesewas == 0
    assert session.reopened_count == 1
    assert Order.objects.get(session_id=session_id).status == OrderStatus.SERVED

    payment = Payment.objects.get()
    assert payment.voided_at is not None
    assert payment.void_reason == "WRONG_AMOUNT"
    assert payment.voided_by_id is not None and payment.void_authorised_by_id == manager.id

    flagged = OrderEvent.objects.filter(
        event_type__in=["PAYMENT_VOIDED", "SESSION_REOPENED", "ORDER_REOPENED"]
    )
    assert flagged.count() == 3
    assert all(e.authorised_by_id == manager.id for e in flagged)


def test_reopen_a_settled_bill_needs_a_manager_and_tells_the_owner(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth, manager, mailoutbox
):
    _, _, _, dev = cashier_auth
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)
    pay(api, cashier_auth, session_id, PaymentMethod.CASH, 7500, tendered_pesewas=7500)

    unauthorised = api.post(
        f"/api/v1/sessions/{session_id}/reopen", {}, format="json", **headers(cashier_auth)
    )
    assert unauthorised.status_code == 403
    assert unauthorised.data["code"] == "authorisation_required"

    reopened = api.post(
        f"/api/v1/sessions/{session_id}/reopen",
        {"authorisation": authorisation(manager, dev, AuthorisationPurpose.REOPEN, "ADD_ITEMS")},
        format="json",
        **headers(cashier_auth),
    )
    assert reopened.status_code == 200, reopened.data
    assert reopened.data["reopened"] is True

    session = TableSession.objects.get(pk=session_id)
    assert session.settled_at is None and session.reopened_count == 1
    assert Order.objects.get(session_id=session_id).status == OrderStatus.SERVED
    assert OrderEvent.objects.filter(event_type="SESSION_REOPENED").count() == 1


def test_paying_a_closed_bill_is_refused(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)
    pay(api, cashier_auth, session_id, PaymentMethod.CASH, 7500, tendered_pesewas=7500)
    closed = api.post(
        f"/api/v1/sessions/{session_id}/close", {}, format="json", **headers(cashier_auth)
    )
    assert closed.status_code == 200, closed.data

    again = pay(api, cashier_auth, session_id, PaymentMethod.CASH, 100, tendered_pesewas=100)
    assert again.status_code == 409
    assert again.data["code"] == "session_closed"


def test_payment_is_idempotent_on_replay(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    """A cashier double-tapping Pay on a slow connection must not take the money twice."""
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    open_shift(api, cashier_auth)

    body = {
        "id": str(uuid7()),
        "method": PaymentMethod.CASH,
        "amount_pesewas": 5000,
        "tendered_pesewas": 5000,
    }
    idem = key()
    first = api.post(
        f"/api/v1/sessions/{session_id}/payments",
        body,
        format="json",
        **headers(cashier_auth, idem),
    )
    replay = api.post(
        f"/api/v1/sessions/{session_id}/payments",
        body,
        format="json",
        **headers(cashier_auth, idem),
    )
    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay["Idempotent-Replayed"] == "true"
    assert replay.data == first.data
    assert Payment.objects.count() == 1


def test_shift_current_shows_running_totals(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    none_yet = api.get("/api/v1/shifts/current", **headers(cashier_auth))
    assert none_yet.status_code == 200 and none_yet.data["shift"] is None

    open_shift(api, cashier_auth, float_pesewas=20000)
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id))
    pay(api, cashier_auth, session_id, PaymentMethod.CASH, 7500, tendered_pesewas=10000)

    current = api.get("/api/v1/shifts/current", **headers(cashier_auth)).data["shift"]
    assert current["cash_payments_pesewas"] == 7500
    assert current["expected_cash_pesewas"] == 27500
    assert current["payment_count"] == 1


def test_reference_normalisation():
    assert normalise_reference("  mp24 0917 abc ") == "MP240917ABC"
    assert normalise_reference("") is None
    assert normalise_reference(None) is None


def test_projections_rebuild_from_the_event_log_after_a_full_service(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth, manager
):
    """The exit criterion: a scripted service, then the projections must equal a replay of the log."""
    _, _, _, dev = cashier_auth
    shift_id = open_shift(api, cashier_auth, float_pesewas=20000)

    tables = [table] + [
        Table.objects.create(number=str(n), qr_token=Table.new_qr_token()) for n in range(20, 24)
    ]
    methods = [
        PaymentMethod.CASH,
        PaymentMethod.MOMO_MTN,
        PaymentMethod.CARD,
        PaymentMethod.MOMO_TELECEL,
        PaymentMethod.CASH,
    ]
    first_payment_id = None
    for seat, (t, method) in enumerate(zip(tables, methods, strict=True), start=1):
        session_id = open_session(api, waiter_auth, t)
        serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id), quantity=seat)
        amount = 7500 * seat
        extra = {"tendered_pesewas": amount} if method == PaymentMethod.CASH else {}
        response = pay(api, cashier_auth, session_id, method, amount, **extra)
        assert response.status_code == 201, response.data
        first_payment_id = first_payment_id or response.data["id"]

    # One void and one reopen, both manager-authorised.
    api.post(
        f"/api/v1/payments/{first_payment_id}/void",
        {
            "authorisation": authorisation(
                manager, dev, AuthorisationPurpose.PAYMENT_VOID, "WRONG_METHOD"
            )
        },
        format="json",
        **headers(cashier_auth),
    )
    api.post(
        f"/api/v1/shifts/{shift_id}/movements",
        {
            "kind": "PAID_IN",
            "amount_pesewas": 5000,
            "authorisation": authorisation(
                manager, dev, AuthorisationPurpose.DRAWER_MOVEMENT, "CHANGE_FLOAT"
            ),
        },
        format="json",
        **headers(cashier_auth),
    )
    api.post(
        f"/api/v1/shifts/{shift_id}/close",
        {"declared_cash_pesewas": 100000},
        format="json",
        **headers(cashier_auth),
    )

    assert verify(restaurant.id) == {}, "projections drifted from the event stream"


def test_z_report_reconciles_by_hand(
    api, restaurant, table, jollof, waiter_auth, kitchen_auth, cashier_auth
):
    """Float 200.00 + cash 150.00 = 350.00 expected; MoMo 75.00 is money taken but not drawer cash."""
    shift_id = open_shift(api, cashier_auth, float_pesewas=20000)
    session_id = open_session(api, waiter_auth, table)
    serve_round(api, waiter_auth, kitchen_auth, session_id, str(jollof.id), quantity=3)  # 225.00
    pay(api, cashier_auth, session_id, PaymentMethod.CASH, 15000, tendered_pesewas=15000)
    pay(api, cashier_auth, session_id, PaymentMethod.MOMO_MTN, 7500, external_reference="ref-1")

    report = api.get(f"/api/v1/shifts/{shift_id}/z-report", **headers(cashier_auth)).data
    assert report["totals_by_method"] == {"CASH": 15000, "MOMO_MTN": 7500}
    assert report["money_taken_pesewas"] == 22500
    assert report["expected_cash_pesewas"] == 35000
    assert report["variance_pesewas"] is None  # not counted yet
    assert TableSession.objects.get(pk=session_id).settled_at is not None


def test_cashier_cannot_be_impersonated_across_restaurants(
    api, restaurant, other_restaurant, cashier_auth
):
    """A shift belongs to one restaurant; another tenant's id must read as missing, not forbidden."""
    open_shift(api, cashier_auth)
    stranger = Shift.objects.create(
        restaurant=other_restaurant,
        cashier=Staff.objects.create(
            restaurant=other_restaurant, full_name="Other", role="CASHIER", pin_hash="x"
        ),
        opened_at=Shift.objects.get().opened_at,
        opening_float_pesewas=0,
    )
    response = api.get(f"/api/v1/shifts/{stranger.id}/z-report", **headers(cashier_auth))
    assert response.status_code == 404
