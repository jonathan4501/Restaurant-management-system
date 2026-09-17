"""
Shared scaffolding for WS05: a till (cashier on an enrolled device), a waiter who can put food on a
bill, and helpers to drive a round of service through the real HTTP endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.authorisation import issue_authorisation
from apps.accounts.models import Staff
from apps.accounts.tokens import issue_staff_token
from apps.core.roles import AuthorisationPurpose
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
def till_device(restaurant, device):
    """One device that may host every role the payment tests need."""
    dev, token = device
    dev.allowed_roles = ["WAITER", "KITCHEN", "CASHIER", "MANAGER"]
    dev.save(update_fields=["allowed_roles"])
    return dev, token


@pytest.fixture
def cashier_auth(restaurant, cashier, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=cashier.id, role="CASHIER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, cashier, dev


@pytest.fixture
def second_cashier(restaurant, pin_hash) -> Staff:
    """A colleague on the same till device: everything of hers is off-limits to the first cashier."""
    return Staff.objects.create(full_name="Kwesi Mensah", role="CASHIER", pin_hash=pin_hash)


@pytest.fixture
def second_cashier_auth(restaurant, second_cashier, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=second_cashier.id, role="CASHIER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, second_cashier, dev


@pytest.fixture
def manager_auth(restaurant, manager, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=manager.id, role="MANAGER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, manager, dev


@pytest.fixture
def waiter_auth(restaurant, waiter, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, waiter, dev


@pytest.fixture
def kitchen_staff(restaurant, pin_hash) -> Staff:
    return Staff.objects.create(full_name="Yaw Boateng", role="KITCHEN", pin_hash=pin_hash)


@pytest.fixture
def kitchen_auth(restaurant, kitchen_staff, till_device):
    dev, token = till_device
    jwt = issue_staff_token(
        staff_id=kitchen_staff.id, role="KITCHEN", restaurant_id=restaurant.id, device_id=dev.id
    )
    return token, jwt, kitchen_staff, dev


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
def table(restaurant) -> Table:
    return Table.objects.create(number="7", qr_token=Table.new_qr_token(), seats=4)


def key() -> str:
    return str(uuid7())


def headers(auth, idempotency_key: str | None = None) -> dict[str, str]:
    token, jwt, _, _ = auth
    return {
        "HTTP_X_DEVICE_TOKEN": token,
        "HTTP_AUTHORIZATION": f"Bearer {jwt}",
        "HTTP_IDEMPOTENCY_KEY": idempotency_key or key(),
    }


def authorisation(manager: Staff, device, purpose: AuthorisationPurpose, reason: str) -> dict:
    """A manager's PIN, already verified: the block a command carrying an override must include."""
    token = issue_authorisation(staff_id=manager.id, device_id=device.id, purpose=purpose)
    return {"token": token, "reason_code": reason}


def serve_round(
    api, waiter_auth, kitchen_auth, session_id: str, menu_item_id: str, quantity: int = 1
) -> dict:
    """A full round: waiter sends it, the kitchen cooks it, it reaches SERVED — payable."""
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
    api.post(
        f"/api/v1/orders/{order_id}/items",
        {
            "id": str(uuid7()),
            "menu_item_id": menu_item_id,
            "quantity": quantity,
            "modifier_ids": [],
        },
        format="json",
        **headers(waiter_auth),
    )
    for step, auth in (
        ("submit", waiter_auth),
        ("ack", kitchen_auth),
        ("ready", kitchen_auth),
        ("serve", waiter_auth),
    ):
        response = api.post(f"/api/v1/orders/{order_id}/{step}", {}, format="json", **headers(auth))
        assert response.status_code == 200, (step, response.data)
    return {"order_id": order_id}


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


def pay(api, cashier_auth, session_id: str, method: str, amount: int, **extra: Any):
    body = {"id": str(uuid7()), "method": method, "amount_pesewas": amount, **extra}
    return api.post(
        f"/api/v1/sessions/{session_id}/payments", body, format="json", **headers(cashier_auth)
    )
