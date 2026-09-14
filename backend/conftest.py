"""
Shared fixtures. Every test that touches tenant-scoped models needs a restaurant in context;
the `restaurant` fixture provides both the row and the context.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from django.utils import timezone

from apps.accounts.models import Device, Restaurant, Staff
from apps.accounts.pins import hash_pin
from apps.accounts.principals import Principal
from apps.accounts.tokens import new_device_token
from apps.core import publisher
from apps.core.commands import CommandContext
from apps.core.idempotency import request_hash
from apps.core.roles import ActorRole
from apps.core.tenancy import restaurant_context
from apps.core.uuid7 import uuid7


@pytest.fixture
def restaurant(db: Any) -> Iterator[Restaurant]:
    r = Restaurant.objects.create(name="RENZY Test")
    with restaurant_context(r.id):
        yield r


@pytest.fixture
def other_restaurant(db: Any) -> Restaurant:
    return Restaurant.objects.create(name="Other Place")


@pytest.fixture
def pin_hash() -> str:
    return hash_pin("1234")


@pytest.fixture
def waiter(restaurant: Restaurant, pin_hash: str) -> Staff:
    return Staff.objects.create(full_name="Kofi", role="WAITER", pin_hash=pin_hash)


@pytest.fixture
def manager(restaurant: Restaurant, pin_hash: str) -> Staff:
    return Staff.objects.create(full_name="Akosua", role="MANAGER", pin_hash=pin_hash)


@pytest.fixture
def device(restaurant: Restaurant) -> tuple[Device, str]:
    token, token_hash = new_device_token()
    d = Device.objects.create(
        label="Tablet 1",
        token_hash=token_hash,
        allowed_roles=["WAITER", "CASHIER"],
        enrolled_at=timezone.now(),
    )
    return d, token


@pytest.fixture
def principal(restaurant: Restaurant, waiter: Staff, device: tuple[Device, str]) -> Principal:
    return Principal("STAFF", restaurant.id, waiter.id, ActorRole.WAITER, device[0].id)


@pytest.fixture
def make_ctx(restaurant: Restaurant, waiter: Staff, device: tuple[Device, str]) -> Any:
    def _make(
        *,
        key: uuid.UUID | None = None,
        body: Any = None,
        path: str = "/api/v1/test",
        restaurant_id: uuid.UUID | None = None,
        actor_role: ActorRole = ActorRole.WAITER,
        authorised_by: uuid.UUID | None = None,
        reason_code: str | None = None,
    ) -> CommandContext:
        return CommandContext(
            restaurant_id=restaurant_id or restaurant.id,
            actor_id=waiter.id,
            actor_role=actor_role,
            device_id=device[0].id,
            idempotency_key=key or uuid7(),
            request_hash=request_hash("POST", path, body or {}),
            client_created_at=datetime(2026, 9, 14, 19, 42, tzinfo=UTC),
            authorised_by=authorised_by,
            reason_code=reason_code,
        )

    return _make


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[tuple[uuid.UUID, list[dict[str, Any]]]]:
    """Captures what the runner would publish to Redis. Use with django_capture_on_commit_callbacks."""
    captured: list[tuple[uuid.UUID, list[dict[str, Any]]]] = []
    monkeypatch.setattr(publisher, "publish", lambda rid, envs: captured.append((rid, envs)))
    return captured
