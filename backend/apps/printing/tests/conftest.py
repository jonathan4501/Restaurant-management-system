"""Scaffolding for WS12: a till that can run a bill to settlement, and a Pi enrolled as a printer."""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Device, Staff
from apps.accounts.tokens import issue_staff_token, new_device_token
from apps.core.uuid7 import uuid7
from apps.floor.models import Table
from apps.menu.models import MenuCategory, MenuItem


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def cashier(restaurant, pin_hash) -> Staff:
    return Staff.objects.create(full_name="Ama Owusu", role="CASHIER", pin_hash=pin_hash)


@pytest.fixture
def kitchen_staff(restaurant, pin_hash) -> Staff:
    return Staff.objects.create(full_name="Yaw Boateng", role="KITCHEN", pin_hash=pin_hash)


@pytest.fixture
def till_device(restaurant, device):
    dev, token = device
    dev.allowed_roles = ["WAITER", "KITCHEN", "CASHIER", "MANAGER"]
    dev.save(update_fields=["allowed_roles"])
    return dev, token


@pytest.fixture
def printer_device(restaurant) -> tuple[Device, str]:
    """The Raspberry Pi. PRINTER only — it hosts no human role."""
    token, token_hash = new_device_token()
    dev = Device.objects.create(
        label="Kitchen Pi",
        token_hash=token_hash,
        allowed_roles=["PRINTER"],
        enrolled_at=timezone.now(),
    )
    return dev, token


@pytest.fixture
def cashier_auth(restaurant, cashier, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=cashier.id, role="CASHIER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, cashier, dev


@pytest.fixture
def waiter_auth(restaurant, waiter, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, waiter, dev


@pytest.fixture
def kitchen_auth(restaurant, kitchen_staff, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=kitchen_staff.id,
        role="KITCHEN",
        restaurant_id=restaurant.id,
        device_id=dev.id,
    )
    return token, jwt, kitchen_staff, dev


@pytest.fixture
def table(restaurant) -> Table:
    return Table.objects.create(number="7", qr_token=Table.new_qr_token(), seats=4)


@pytest.fixture
def jollof(restaurant) -> MenuItem:
    category = MenuCategory.objects.create(name="Mains")
    return MenuItem.objects.create(
        category=category,
        name="Jollof Rice with Grilled Chicken",
        price_pesewas=7500,
        prep_station="KITCHEN",
    )


@pytest.fixture
def beer(restaurant) -> MenuItem:
    category = MenuCategory.objects.create(name="Drinks")
    return MenuItem.objects.create(
        category=category, name="Club Beer", price_pesewas=1500, prep_station="BAR"
    )


def key() -> str:
    return str(uuid7())


def headers(auth, idempotency_key: str | None = None) -> dict[str, str]:
    token, jwt, _, _ = auth
    return {
        "HTTP_X_DEVICE_TOKEN": token,
        "HTTP_AUTHORIZATION": f"Bearer {jwt}",
        "HTTP_IDEMPOTENCY_KEY": idempotency_key or key(),
    }


def printer_headers(printer_device) -> dict[str, str]:
    """The bridge presents a device token and nothing else — no staff JWT."""
    _, token = printer_device
    return {"HTTP_X_DEVICE_TOKEN": token}


def open_session(api, waiter_auth, table) -> str:
    session_id = str(uuid7())
    response = api.post(
        "/api/v1/sessions",
        {"id": session_id, "table_id": str(table.id), "party_size": 2},
        format="json",
        **headers(waiter_auth),
    )
    assert response.status_code == 201, response.data
    return session_id


def serve_round(api, waiter_auth, kitchen_auth, session_id: str, items) -> str:
    """A full round through the real endpoints: sent, cooked, served — so it is payable."""
    order_id = str(uuid7())
    assert (
        api.post(
            "/api/v1/orders",
            {"id": order_id, "session_id": session_id},
            format="json",
            **headers(waiter_auth),
        ).status_code
        == 201
    )
    for menu_item, quantity in items:
        response = api.post(
            f"/api/v1/orders/{order_id}/items",
            {
                "id": str(uuid7()),
                "menu_item_id": str(menu_item.id),
                "quantity": quantity,
                "modifier_ids": [],
            },
            format="json",
            **headers(waiter_auth),
        )
        assert response.status_code in (200, 201), response.data
    for step, auth in (
        ("submit", waiter_auth),
        ("ack", kitchen_auth),
        ("ready", kitchen_auth),
        ("serve", waiter_auth),
    ):
        response = api.post(f"/api/v1/orders/{order_id}/{step}", {}, format="json", **headers(auth))
        assert response.status_code == 200, (step, response.data)
    return order_id


def open_shift(api, cashier_auth, float_pesewas: int = 20000) -> str:
    shift_id = str(uuid7())
    response = api.post(
        "/api/v1/shifts",
        {"id": shift_id, "opening_float_pesewas": float_pesewas},
        format="json",
        **headers(cashier_auth),
    )
    assert response.status_code == 201, response.data
    return shift_id


def pay(api, cashier_auth, session_id: str, method: str, amount: int, **extra):
    body = {"id": str(uuid7()), "method": method, "amount_pesewas": amount, **extra}
    return api.post(
        f"/api/v1/sessions/{session_id}/payments", body, format="json", **headers(cashier_auth)
    )
