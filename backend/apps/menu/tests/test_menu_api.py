"""GET /menu ETag round-trip and cache invalidation."""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.test import override_settings
from django.urls import include, path
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.menu.cache import compute_etag, get_cached_menu, invalidate_menu_cache, set_cached_menu
from apps.menu.models import MenuItem
from apps.menu.serializers import build_menu_payload
from apps.menu.views import MenuView

factory = APIRequestFactory()

urlpatterns = [
    path("api/v1/", include("apps.menu.urls")),
]


def _get(principal: Any, **headers: str) -> Any:
    request = factory.get("/api/v1/menu", **headers)
    request.principal = principal
    request.auth_error = None
    force_authenticate(request, user=principal)
    response = MenuView.as_view()(request)
    response.render()
    return response


@pytest.mark.django_db
@override_settings(ROOT_URLCONF=__name__)
def test_menu_returns_categories_items_and_etag(
    restaurant, linked_guinea, kitchen_principal
) -> None:
    response = _get(kitchen_principal)
    assert response.status_code == 200
    assert "ETag" in response
    body = response.data
    assert len(body["categories"]) == 1
    item = body["categories"][0]["items"][0]
    assert item["name"] == "Grilled Guinea Fowl"
    assert item["price_pesewas"] == 15000
    assert item["is_available"] is True
    assert item["prep_station"] == "GRILL"
    assert len(item["modifier_groups"]) == 2
    pepper = item["modifier_groups"][0]
    assert pepper["selection"] == "ONE"
    assert pepper["is_required"] is True
    assert any(m["name"] == "Mild" for m in pepper["modifiers"])


@pytest.mark.django_db
def test_etag_304_round_trip(restaurant, linked_guinea, kitchen_principal) -> None:
    first = _get(kitchen_principal)
    assert first.status_code == 200
    etag = first["ETag"]
    again = _get(kitchen_principal, HTTP_IF_NONE_MATCH=etag)
    assert again.status_code == 304
    assert again["ETag"] == etag


@pytest.mark.django_db
def test_menu_write_invalidates_cache(restaurant, linked_guinea, kitchen_principal) -> None:
    first = _get(kitchen_principal)
    assert first.status_code == 200
    cached = get_cached_menu(restaurant.id)
    assert cached is not None

    # Admin-style write: flip name → post_save signal must drop the cache.
    linked_guinea.name = "Guinea Fowl (updated)"
    linked_guinea.save()
    assert get_cached_menu(restaurant.id) is None

    second = _get(kitchen_principal)
    assert second.status_code == 200
    assert second.data["categories"][0]["items"][0]["name"] == "Guinea Fowl (updated)"
    # Body changed → ETag must change.
    assert second["ETag"] != first["ETag"]


@pytest.mark.django_db
def test_inactive_items_excluded(restaurant, guinea_fowl, kitchen_principal) -> None:
    guinea_fowl.is_active = False
    guinea_fowl.save()
    response = _get(kitchen_principal)
    assert response.data["categories"][0]["items"] == []


@pytest.mark.django_db
def test_compute_etag_stable(restaurant, linked_guinea) -> None:
    body = build_menu_payload()
    assert compute_etag(body) == compute_etag(json.loads(json.dumps(body)))


@pytest.mark.django_db
def test_cached_body_served(restaurant, linked_guinea, kitchen_principal) -> None:
    body = {"categories": [{"id": "x", "name": "Stub", "sort_order": 0, "items": []}]}
    etag = compute_etag(body)
    set_cached_menu(restaurant.id, body, etag)
    response = _get(kitchen_principal)
    assert response.data == body
    invalidate_menu_cache(restaurant.id)
    # Prove the live item still exists so we didn't accidentally wipe the DB.
    assert MenuItem.objects.filter(name="Grilled Guinea Fowl").exists()
