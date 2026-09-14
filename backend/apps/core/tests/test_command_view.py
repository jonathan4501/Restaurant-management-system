"""CommandView end-to-end through DRF: headers, error shape, replay header, authorisation block."""

from __future__ import annotations

import json
from typing import Any

import pytest
from rest_framework import serializers
from rest_framework.test import APIRequestFactory

from apps.accounts.authorisation import issue_authorisation
from apps.core.commands import CommandContext, CommandOutcome, EventDraft
from apps.core.roles import ActorRole, AggregateType, AuthorisationPurpose
from apps.core.uuid7 import uuid7
from apps.core.views import CommandView
from apps.orders.events import EventType
from apps.orders.models import OrderEvent


class OpenTableInput(serializers.Serializer):
    table_number = serializers.CharField()


class OpenTableView(CommandView):
    allowed_roles = (ActorRole.WAITER, ActorRole.MANAGER)
    input_serializer = OpenTableInput

    def handle(self, ctx: CommandContext, data: dict[str, Any], **kwargs: Any) -> CommandOutcome:
        draft = EventDraft(
            AggregateType.SESSION,
            uuid7(),
            EventType.SESSION_OPENED,
            {"table_number": data["table_number"]},
        )
        return CommandOutcome(
            events=[draft], response={"table_number": data["table_number"]}, status=201
        )


class AuthorisedView(OpenTableView):
    authorisation_purpose = AuthorisationPurpose.DRAWER_MOVEMENT


factory = APIRequestFactory()


def post(view: Any, principal: Any, body: dict[str, Any], **headers: str) -> Any:
    request = factory.post(
        "/api/v1/test", data=json.dumps(body), content_type="application/json", **headers
    )
    request.principal = principal
    request.auth_error = None
    response = view(request)
    response.render()  # headers such as Content-Type are set at render time
    return response


@pytest.mark.django_db
def test_missing_idempotency_key_is_400_problem(restaurant, principal) -> None:
    response = post(OpenTableView.as_view(), principal, {"table_number": "7"})
    assert response.status_code == 400
    assert response["Content-Type"] == "application/problem+json"
    assert response.data["code"] == "idempotency_key_missing"


@pytest.mark.django_db
def test_non_v7_key_is_rejected(restaurant, principal) -> None:
    response = post(
        OpenTableView.as_view(),
        principal,
        {"table_number": "7"},
        HTTP_IDEMPOTENCY_KEY="c7d0e8a0-0000-4000-8000-000000000000",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_command_runs_and_replays_with_header(restaurant, principal) -> None:
    key = str(uuid7())
    first = post(
        OpenTableView.as_view(), principal, {"table_number": "7"}, HTTP_IDEMPOTENCY_KEY=key
    )
    assert first.status_code == 201
    assert first.data == {"table_number": "7"}
    assert "Idempotent-Replayed" not in first

    again = post(
        OpenTableView.as_view(), principal, {"table_number": "7"}, HTTP_IDEMPOTENCY_KEY=key
    )
    assert again.status_code == 201
    assert again["Idempotent-Replayed"] == "true"
    assert OrderEvent.objects.count() == 1


@pytest.mark.django_db
def test_validation_error_is_problem_json(restaurant, principal) -> None:
    response = post(OpenTableView.as_view(), principal, {}, HTTP_IDEMPOTENCY_KEY=str(uuid7()))
    assert response.status_code == 400
    assert response.data["code"] == "validation_error"
    assert "table_number" in response.data["errors"]


@pytest.mark.django_db
def test_role_not_allowed_is_403(restaurant, principal) -> None:
    kitchen = principal.__class__(
        "STAFF", principal.restaurant_id, principal.actor_id, ActorRole.KITCHEN, principal.device_id
    )
    response = post(
        OpenTableView.as_view(), kitchen, {"table_number": "7"}, HTTP_IDEMPOTENCY_KEY=str(uuid7())
    )
    assert response.status_code == 403
    assert response.data["code"] == "role_not_allowed"


@pytest.mark.django_db
def test_unauthenticated_is_401(restaurant) -> None:
    response = post(
        OpenTableView.as_view(), None, {"table_number": "7"}, HTTP_IDEMPOTENCY_KEY=str(uuid7())
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_authorisation_block_required_consumed_and_recorded(restaurant, principal, manager) -> None:
    view = AuthorisedView.as_view()
    denied = post(view, principal, {"table_number": "7"}, HTTP_IDEMPOTENCY_KEY=str(uuid7()))
    assert denied.status_code == 403
    assert denied.data["code"] == "authorisation_required"

    token = issue_authorisation(
        staff_id=manager.id,
        device_id=principal.device_id,
        purpose=AuthorisationPurpose.DRAWER_MOVEMENT,
    )
    body = {"table_number": "7", "authorisation": {"token": token, "reason_code": "NO_SALE"}}
    ok = post(view, principal, body, HTTP_IDEMPOTENCY_KEY=str(uuid7()))
    assert ok.status_code == 201, ok.data
    event = OrderEvent.objects.get()
    assert event.actor_id == principal.actor_id  # the waiter acted
    assert event.authorised_by_id == manager.id  # the manager authorised — two names
    assert event.reason_code == "NO_SALE"

    reused = post(view, principal, body, HTTP_IDEMPOTENCY_KEY=str(uuid7()))
    assert reused.status_code == 403  # single use
    assert reused.data["code"] == "authorisation_invalid"


@pytest.mark.django_db
def test_authorisation_purpose_mismatch(restaurant, principal, manager) -> None:
    token = issue_authorisation(
        staff_id=manager.id, device_id=principal.device_id, purpose=AuthorisationPurpose.DISCOUNT
    )
    body = {"table_number": "7", "authorisation": {"token": token, "reason_code": "X"}}
    response = post(AuthorisedView.as_view(), principal, body, HTTP_IDEMPOTENCY_KEY=str(uuid7()))
    assert response.status_code == 403
    assert response.data["code"] == "authorisation_purpose_mismatch"
