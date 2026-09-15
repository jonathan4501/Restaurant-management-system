"""86 / restore / price-change commands + projections + publish."""

from __future__ import annotations

import json
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.authorisation import issue_authorisation
from apps.core.roles import AuthorisationPurpose
from apps.core.uuid7 import uuid7
from apps.menu.views import EightySixView, MenuView, PriceChangeView, RestoreView
from apps.orders.events import EventType
from apps.orders.models import OrderEvent

factory = APIRequestFactory()


def _post(
    view_cls: type,
    principal: Any,
    *,
    item_id: Any,
    body: dict[str, Any] | None = None,
    **headers: str,
) -> Any:
    request = factory.post(
        f"/api/v1/menu/items/{item_id}/x",
        data=json.dumps(body or {}),
        content_type="application/json",
        **headers,
    )
    request.principal = principal
    request.auth_error = None
    force_authenticate(request, user=principal)
    response = view_cls.as_view()(request, item_id=item_id)
    response.render()
    return response


def _get_menu(principal: Any) -> Any:
    request = factory.get("/api/v1/menu")
    request.principal = principal
    request.auth_error = None
    force_authenticate(request, user=principal)
    response = MenuView.as_view()(request)
    response.render()
    return response


@pytest.mark.django_db(transaction=True)
def test_86_flips_projection_menu_and_publishes(
    restaurant,
    guinea_fowl,
    kitchen_principal,
    published,
    django_capture_on_commit_callbacks,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        response = _post(
            EightySixView,
            kitchen_principal,
            item_id=guinea_fowl.id,
            HTTP_IDEMPOTENCY_KEY=str(uuid7()),
        )
    assert response.status_code == 200, response.data
    assert response.data["is_available"] is False

    guinea_fowl.refresh_from_db()
    assert guinea_fowl.is_available is False

    menu = _get_menu(kitchen_principal)
    assert menu.data["categories"][0]["items"][0]["is_available"] is False

    event = OrderEvent.objects.get()
    assert event.event_type == EventType.ITEM_86ED
    assert event.payload["menu_item_id"] == str(guinea_fowl.id)
    assert event.payload["is_available"] is False

    assert len(published) == 1
    _rid, envelopes = published[0]
    assert envelopes[0]["type"] == EventType.ITEM_86ED
    assert envelopes[0]["payload"]["is_available"] is False


@pytest.mark.django_db(transaction=True)
def test_restore_flips_back(
    restaurant, guinea_fowl, kitchen_principal, django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        _post(
            EightySixView,
            kitchen_principal,
            item_id=guinea_fowl.id,
            HTTP_IDEMPOTENCY_KEY=str(uuid7()),
        )
        response = _post(
            RestoreView,
            kitchen_principal,
            item_id=guinea_fowl.id,
            HTTP_IDEMPOTENCY_KEY=str(uuid7()),
        )
    assert response.status_code == 200
    guinea_fowl.refresh_from_db()
    assert guinea_fowl.is_available is True
    assert OrderEvent.objects.filter(event_type=EventType.ITEM_RESTORED).exists()


@pytest.mark.django_db(transaction=True)
def test_price_change_during_service_requires_authorisation(
    restaurant, guinea_fowl, manager_principal, manager, django_capture_on_commit_callbacks
) -> None:
    restaurant.service_start = time(0, 0)
    restaurant.service_end = time(23, 59, 59)
    restaurant.timezone = "UTC"
    restaurant.save()

    denied = _post(
        PriceChangeView,
        manager_principal,
        item_id=guinea_fowl.id,
        body={"price_pesewas": 16000},
        HTTP_IDEMPOTENCY_KEY=str(uuid7()),
    )
    assert denied.status_code == 403
    assert denied.data["code"] == "authorisation_required"

    token = issue_authorisation(
        staff_id=manager.id,
        device_id=manager_principal.device_id,
        purpose=AuthorisationPurpose.PRICE_CHANGE_IN_SERVICE,
    )
    with django_capture_on_commit_callbacks(execute=True):
        ok = _post(
            PriceChangeView,
            manager_principal,
            item_id=guinea_fowl.id,
            body={
                "price_pesewas": 16000,
                "authorisation": {"token": token, "reason_code": "SUPPLIER_COST"},
            },
            HTTP_IDEMPOTENCY_KEY=str(uuid7()),
        )
    assert ok.status_code == 200, ok.data
    assert ok.data["old_price_pesewas"] == 15000
    assert ok.data["new_price_pesewas"] == 16000
    assert ok.data["during_service"] is True

    guinea_fowl.refresh_from_db()
    assert guinea_fowl.price_pesewas == 16000

    event = OrderEvent.objects.get(event_type=EventType.PRICE_CHANGED)
    assert event.payload["old_price_pesewas"] == 15000
    assert event.payload["new_price_pesewas"] == 16000
    assert event.payload["during_service"] is True
    assert event.authorised_by_id == manager.id
    assert event.reason_code == "SUPPLIER_COST"


@pytest.mark.django_db(transaction=True)
def test_price_change_outside_service_needs_no_authorisation(
    restaurant, guinea_fowl, manager_principal, django_capture_on_commit_callbacks, monkeypatch
) -> None:
    restaurant.service_start = time(11, 0)
    restaurant.service_end = time(23, 0)
    restaurant.timezone = "Africa/Accra"
    restaurant.save()

    # Freeze "now" to 09:00 Accra — outside service.
    frozen = datetime(2026, 9, 14, 9, 0, tzinfo=ZoneInfo("Africa/Accra"))
    monkeypatch.setattr("apps.menu.service_hours.timezone.now", lambda: frozen)

    with django_capture_on_commit_callbacks(execute=True):
        ok = _post(
            PriceChangeView,
            manager_principal,
            item_id=guinea_fowl.id,
            body={"price_pesewas": 14000},
            HTTP_IDEMPOTENCY_KEY=str(uuid7()),
        )
    assert ok.status_code == 200, ok.data
    assert ok.data["during_service"] is False
    guinea_fowl.refresh_from_db()
    assert guinea_fowl.price_pesewas == 14000


@pytest.mark.django_db
def test_waiter_cannot_86(restaurant, guinea_fowl, principal) -> None:
    response = _post(
        EightySixView,
        principal,
        item_id=guinea_fowl.id,
        HTTP_IDEMPOTENCY_KEY=str(uuid7()),
    )
    assert response.status_code == 403
    assert response.data["code"] == "role_not_allowed"
