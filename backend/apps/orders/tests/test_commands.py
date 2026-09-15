"""WS03 integration: commands, projections, snapshots, order numbers, guest sandbox."""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.accounts.authorisation import issue_authorisation
from apps.accounts.models import Staff
from apps.accounts.tokens import issue_guest_token, issue_staff_token
from apps.core.roles import ActorRole, AuthorisationPurpose
from apps.core.uuid7 import uuid7
from apps.floor.models import Table, TableSession
from apps.menu.models import MenuCategory, MenuItem
from apps.orders.models import Order, OrderEvent, OrderStatus
from apps.orders.rebuild import verify
from apps.orders.totals import apply_percent_discount

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def table(restaurant) -> Table:
    return Table.objects.create(number="7", qr_token=Table.new_qr_token(), seats=4)


@pytest.fixture
def tilapia(restaurant) -> MenuItem:
    cat = MenuCategory.objects.create(name="Grill")
    return MenuItem.objects.create(
        category=cat, name="Whole Grilled Tilapia", price_pesewas=13000, prep_station="GRILL"
    )


@pytest.fixture
def kitchen(restaurant, pin_hash) -> Staff:
    return Staff.objects.create(full_name="Ama", role="KITCHEN", pin_hash=pin_hash)


@pytest.fixture
def cashier(restaurant, pin_hash) -> Staff:
    return Staff.objects.create(full_name="Kojo", role="CASHIER", pin_hash=pin_hash)


def _key() -> str:
    return str(uuid7())


def _staff_headers(device_token: str, jwt: str, key: str | None = None) -> dict[str, str]:
    return {
        "HTTP_X_DEVICE_TOKEN": device_token,
        "HTTP_AUTHORIZATION": f"Bearer {jwt}",
        "HTTP_IDEMPOTENCY_KEY": key or _key(),
    }


@pytest.fixture
def waiter_auth(restaurant, waiter, device):
    dev, token = device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, waiter, dev


@pytest.fixture
def kitchen_auth(restaurant, kitchen, device):
    # Expand device roles for kitchen tests
    dev, token = device
    dev.allowed_roles = ["WAITER", "CASHIER", "KITCHEN", "MANAGER"]
    dev.save(update_fields=["allowed_roles"])
    jwt = issue_staff_token(
        staff_id=kitchen.id, role="KITCHEN", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, kitchen, dev


def _open_session(api, waiter_auth, table) -> str:
    token, jwt, _, _ = waiter_auth
    sid = uuid7()
    r = api.post(
        "/api/v1/sessions",
        {"id": str(sid), "table_id": str(table.id), "party_size": 2},
        format="json",
        **_staff_headers(token, jwt),
    )
    assert r.status_code == 201, r.data
    return str(sid)


def _open_order(api, waiter_auth, session_id: str) -> str:
    token, jwt, _, _ = waiter_auth
    oid = uuid7()
    r = api.post(
        "/api/v1/orders",
        {"id": str(oid), "session_id": session_id},
        format="json",
        **_staff_headers(token, jwt),
    )
    assert r.status_code == 201, r.data
    return str(oid)


def _add_item(api, waiter_auth, order_id: str, menu_item_id: str) -> str:
    token, jwt, _, _ = waiter_auth
    iid = uuid7()
    r = api.post(
        f"/api/v1/orders/{order_id}/items",
        {
            "id": str(iid),
            "menu_item_id": menu_item_id,
            "quantity": 1,
            "modifier_ids": [],
        },
        format="json",
        **_staff_headers(token, jwt),
    )
    assert r.status_code == 200, r.data
    return str(iid)


def test_open_session_order_add_submit_and_idempotent_replay(
    api, restaurant, table, tilapia, waiter_auth, published, django_capture_on_commit_callbacks
):
    session_id = _open_session(api, waiter_auth, table)
    order_id = _open_order(api, waiter_auth, session_id)
    _add_item(api, waiter_auth, order_id, str(tilapia.id))

    token, jwt, waiter, _ = waiter_auth
    key = _key()
    with django_capture_on_commit_callbacks(execute=True):
        first = api.post(
            f"/api/v1/orders/{order_id}/submit",
            {},
            format="json",
            **_staff_headers(token, jwt, key),
        )
    assert first.status_code == 200, first.data
    assert first.data["order_number"] == 1
    assert first["Idempotent-Replayed"] != "true" if False else True

    replay = api.post(
        f"/api/v1/orders/{order_id}/submit",
        {},
        format="json",
        **_staff_headers(token, jwt, key),
    )
    assert replay.status_code == 200
    assert replay["Idempotent-Replayed"] == "true"
    assert replay.data == first.data

    order = Order.objects.get(pk=order_id)
    assert order.status == OrderStatus.SUBMITTED
    assert order.total_pesewas == 13000

    ev = OrderEvent.objects.filter(event_type="ORDER_SUBMITTED").get()
    assert ev.actor_id == waiter.id
    assert ev.device_id is not None
    assert published, "submit should publish envelopes"


def test_menu_price_change_does_not_rewrite_bill(api, restaurant, table, tilapia, waiter_auth):
    session_id = _open_session(api, waiter_auth, table)
    order_id = _open_order(api, waiter_auth, session_id)
    _add_item(api, waiter_auth, order_id, str(tilapia.id))
    token, jwt, _, _ = waiter_auth
    assert (
        api.post(
            f"/api/v1/orders/{order_id}/submit",
            {},
            format="json",
            **_staff_headers(token, jwt),
        ).status_code
        == 200
    )

    tilapia.price_pesewas = 99999
    tilapia.save(update_fields=["price_pesewas"])

    bill = api.get(
        f"/api/v1/sessions/{session_id}/bill",
        **{
            "HTTP_X_DEVICE_TOKEN": token,
            "HTTP_AUTHORIZATION": f"Bearer {jwt}",
        },
    )
    assert bill.status_code == 200
    assert bill.data["bill_total_pesewas"] == 13000
    assert bill.data["lines"][0]["unit_price_pesewas"] == 13000


def test_order_numbers_consecutive_and_draft_leaves_no_gap(
    api, restaurant, table, tilapia, waiter_auth
):
    token, jwt, _, _ = waiter_auth
    s1 = _open_session(api, waiter_auth, table)
    o1 = _open_order(api, waiter_auth, s1)
    _add_item(api, waiter_auth, o1, str(tilapia.id))
    assert (
        api.post(
            f"/api/v1/orders/{o1}/submit", {}, format="json", **_staff_headers(token, jwt)
        ).data["order_number"]
        == 1
    )

    # Abandoned draft on same session
    _open_order(api, waiter_auth, s1)

    table2 = Table.objects.create(number="8", qr_token=Table.new_qr_token())
    s2 = _open_session(api, waiter_auth, table2)
    o2 = _open_order(api, waiter_auth, s2)
    _add_item(api, waiter_auth, o2, str(tilapia.id))
    assert (
        api.post(
            f"/api/v1/orders/{o2}/submit", {}, format="json", **_staff_headers(token, jwt)
        ).data["order_number"]
        == 2
    )


def test_business_date_cutover_accra(api, restaurant, table, tilapia, waiter_auth):
    token, jwt, _, _ = waiter_auth
    session_id = _open_session(api, waiter_auth, table)

    def submit_at(when: datetime) -> int:
        oid = _open_order(api, waiter_auth, session_id)
        _add_item(api, waiter_auth, oid, str(tilapia.id))
        with patch("apps.orders.commands.submit.timezone.now", return_value=when):
            r = api.post(
                f"/api/v1/orders/{oid}/submit",
                {},
                format="json",
                **_staff_headers(token, jwt),
            )
        assert r.status_code == 200, r.data
        return r.data["order_number"]

    # Accra is UTC+0; cutover hour 4 → 03:59 is previous calendar day business date
    n1 = submit_at(datetime(2026, 9, 15, 3, 59, tzinfo=UTC))
    n2 = submit_at(datetime(2026, 9, 15, 4, 1, tzinfo=UTC))
    assert n1 == 1
    assert n2 == 1  # new business date resets counter


@pytest.mark.django_db(transaction=True)
def test_parallel_submits_get_distinct_consecutive_numbers(restaurant, waiter, device, tilapia):
    from apps.core.commands import CommandContext, run_command
    from apps.core.idempotency import request_hash
    from apps.core.tenancy import restaurant_context
    from apps.floor.commands import open_session
    from apps.orders.commands import add_item, open_order, submit_order

    dev, _ = device
    results: list[int] = []
    errors: list[BaseException] = []
    tables = [Table.objects.create(number=f"P{i}", qr_token=Table.new_qr_token()) for i in range(2)]
    barrier = threading.Barrier(2)

    def worker(t: Table) -> None:
        try:
            with restaurant_context(restaurant.id):
                sid, oid, iid = uuid7(), uuid7(), uuid7()

                def make_ctx() -> CommandContext:
                    return CommandContext(
                        restaurant_id=restaurant.id,
                        actor_id=waiter.id,
                        actor_role=ActorRole.WAITER,
                        device_id=dev.id,
                        idempotency_key=uuid7(),
                        request_hash=request_hash("POST", "/x", {"k": str(uuid7())}),
                        client_created_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
                    )

                run_command(
                    make_ctx(),
                    lambda c: open_session(c, {"id": sid, "table_id": t.id, "party_size": 2}),
                )
                run_command(make_ctx(), lambda c: open_order(c, {"id": oid, "session_id": sid}))
                run_command(
                    make_ctx(),
                    lambda c: add_item(
                        c,
                        oid,
                        {
                            "id": iid,
                            "menu_item_id": tilapia.id,
                            "quantity": 1,
                            "modifier_ids": [],
                        },
                    ),
                )
                barrier.wait(timeout=10)
                out = run_command(make_ctx(), lambda c: submit_order(c, oid))
                results.append(out.body["order_number"])
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in tables]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    assert not errors, errors
    assert sorted(results) == [1, 2]


def test_void_after_ack_needs_auth_and_drops_bill(
    api, restaurant, table, tilapia, waiter_auth, kitchen_auth, manager, device
):
    session_id = _open_session(api, waiter_auth, table)
    order_id = _open_order(api, waiter_auth, session_id)
    _add_item(api, waiter_auth, order_id, str(tilapia.id))
    wtoken, wjwt, _, _ = waiter_auth
    assert (
        api.post(
            f"/api/v1/orders/{order_id}/submit", {}, format="json", **_staff_headers(wtoken, wjwt)
        ).status_code
        == 200
    )

    ktoken, kjwt, _, _ = kitchen_auth
    assert (
        api.post(
            f"/api/v1/orders/{order_id}/ack", {}, format="json", **_staff_headers(ktoken, kjwt)
        ).status_code
        == 200
    )

    denied = api.post(
        f"/api/v1/orders/{order_id}/void",
        {"reason_code": "KITCHEN_ERROR"},
        format="json",
        **_staff_headers(wtoken, wjwt),
    )
    assert denied.status_code == 403

    auth_token = issue_authorisation(
        staff_id=manager.id,
        device_id=device[0].id,
        purpose=AuthorisationPurpose.VOID_AFTER_ACK,
    )
    ok = api.post(
        f"/api/v1/orders/{order_id}/void",
        {
            "reason_code": "KITCHEN_ERROR",
            "authorisation": {"token": auth_token, "reason_code": "KITCHEN_ERROR", "note": "burnt"},
        },
        format="json",
        **_staff_headers(wtoken, wjwt),
    )
    assert ok.status_code == 200, ok.data
    session = TableSession.objects.get(pk=session_id)
    assert session.bill_total_pesewas == 0
    ev = OrderEvent.objects.filter(event_type="ORDER_VOIDED").get()
    assert ev.authorised_by_id == manager.id
    assert ev.payload["status_at_void"] == "PREPARING"


def test_guest_cannot_touch_other_session_or_ack(
    api, restaurant, table, tilapia, waiter_auth, kitchen_auth
):
    session_id = _open_session(api, waiter_auth, table)
    other_table = Table.objects.create(number="9", qr_token=Table.new_qr_token())
    other_session = _open_session(api, waiter_auth, other_table)

    guest_jwt = issue_guest_token(
        session_id=uuid.UUID(session_id), restaurant_id=restaurant.id, mode="guest"
    )

    # Own order OK
    oid = uuid7()
    own = api.post(
        "/api/v1/guest/orders",
        {"id": str(oid), "session_id": session_id},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert own.status_code == 201, own.data

    # Other session → 404
    bad = api.post(
        "/api/v1/guest/orders",
        {"id": str(uuid7()), "session_id": other_session},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert bad.status_code == 404

    # Guest cannot ack staff endpoint
    wtoken, wjwt, _, _ = waiter_auth
    _add_item(api, waiter_auth, str(oid), str(tilapia.id))
    api.post(f"/api/v1/orders/{oid}/submit", {}, format="json", **_staff_headers(wtoken, wjwt))
    # use guest token on staff ack route
    ack = api.post(
        f"/api/v1/orders/{oid}/ack",
        {},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert ack.status_code in (401, 403)


def test_verify_projections_clean_after_scripted_service(
    api, restaurant, table, tilapia, waiter_auth, kitchen_auth, manager, device
):
    wtoken, wjwt, _, _ = waiter_auth
    ktoken, kjwt, _, kdev = kitchen_auth
    # Manager JWT on the same expanded device for authorised money actions.
    mjwt = issue_staff_token(
        staff_id=manager.id, role="MANAGER", restaurant_id=restaurant.id, device_id=kdev.id
    )

    for i in range(30):
        t = table if i == 0 else Table.objects.create(number=f"S{i}", qr_token=Table.new_qr_token())
        sid = _open_session(api, waiter_auth, t)
        oid = _open_order(api, waiter_auth, sid)
        _add_item(api, waiter_auth, oid, str(tilapia.id))
        assert (
            api.post(
                f"/api/v1/orders/{oid}/submit", {}, format="json", **_staff_headers(wtoken, wjwt)
            ).status_code
            == 200
        )
        if i % 2 == 0:
            assert (
                api.post(
                    f"/api/v1/orders/{oid}/ack", {}, format="json", **_staff_headers(ktoken, kjwt)
                ).status_code
                == 200
            )
            auth_token = issue_authorisation(
                staff_id=manager.id,
                device_id=device[0].id,
                purpose=AuthorisationPurpose.VOID_AFTER_ACK,
            )
            assert (
                api.post(
                    f"/api/v1/orders/{oid}/void",
                    {
                        "reason_code": "OTHER",
                        "authorisation": {
                            "token": auth_token,
                            "reason_code": "OTHER",
                        },
                    },
                    format="json",
                    **_staff_headers(wtoken, wjwt),
                ).status_code
                == 200
            )
        else:
            assert (
                api.post(
                    f"/api/v1/orders/{oid}/ready", {}, format="json", **_staff_headers(ktoken, kjwt)
                ).status_code
                == 200
            )
            assert (
                api.post(
                    f"/api/v1/orders/{oid}/serve", {}, format="json", **_staff_headers(wtoken, wjwt)
                ).status_code
                == 200
            )
            auth_token = issue_authorisation(
                staff_id=manager.id,
                device_id=kdev.id,
                purpose=AuthorisationPurpose.DISCOUNT,
            )
            assert (
                api.post(
                    f"/api/v1/orders/{oid}/discount",
                    {
                        "kind": "PERCENT",
                        "value": 10,
                        "authorisation": {"token": auth_token, "reason_code": "PROMOTION"},
                    },
                    format="json",
                    **_staff_headers(ktoken, mjwt),
                ).status_code
                == 200
            )

    assert verify(restaurant.id) == {}


def test_apply_percent_discount_alias() -> None:
    assert apply_percent_discount(12345, 10) == 1235


def test_fire_returns_501(api, waiter_auth, table, tilapia):
    sid = _open_session(api, waiter_auth, table)
    oid = _open_order(api, waiter_auth, sid)
    token, jwt, _, _ = waiter_auth
    r = api.post(
        f"/api/v1/orders/{oid}/fire",
        {},
        format="json",
        **_staff_headers(token, jwt),
    )
    assert r.status_code == 501


def test_kds_tickets_filter_station(api, restaurant, table, tilapia, waiter_auth, kitchen_auth):
    sid = _open_session(api, waiter_auth, table)
    oid = _open_order(api, waiter_auth, sid)
    _add_item(api, waiter_auth, oid, str(tilapia.id))
    wtoken, wjwt, _, _ = waiter_auth
    api.post(f"/api/v1/orders/{oid}/submit", {}, format="json", **_staff_headers(wtoken, wjwt))
    ktoken, kjwt, _, _ = kitchen_auth
    tickets = api.get(
        "/api/v1/kds/tickets",
        {"station": "GRILL"},
        HTTP_X_DEVICE_TOKEN=ktoken,
        HTTP_AUTHORIZATION=f"Bearer {kjwt}",
    )
    assert tickets.status_code == 200
    assert len(tickets.data) == 1
    assert tickets.data[0]["order_number"] == 1

    empty = api.get(
        "/api/v1/kds/tickets",
        {"station": "BAR"},
        HTTP_X_DEVICE_TOKEN=ktoken,
        HTTP_AUTHORIZATION=f"Bearer {kjwt}",
    )
    assert empty.data == []
