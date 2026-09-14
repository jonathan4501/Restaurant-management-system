import pytest
from django.test import RequestFactory
from django.utils import timezone

from apps.accounts.models import Device
from apps.accounts.pins import hash_pin, verify_pin
from apps.accounts.principals import AuthError, resolve_principal
from apps.accounts.tokens import issue_guest_token, issue_staff_token
from apps.core.uuid7 import uuid7

rf = RequestFactory()


def test_pin_hashing_is_argon2_and_verifies() -> None:
    h = hash_pin("4321")
    assert h.startswith("$argon2id$")
    assert verify_pin(h, "4321")
    assert not verify_pin(h, "1234")


@pytest.mark.parametrize("bad", ["123", "1234567", "12a4", ""])
def test_pin_format(bad: str) -> None:
    with pytest.raises(ValueError):
        hash_pin(bad)


@pytest.mark.django_db
def test_no_credentials_means_no_principal(restaurant) -> None:
    assert resolve_principal(rf.get("/")) is None


@pytest.mark.django_db
def test_staff_token_on_its_device(restaurant, waiter, device) -> None:
    dev, token = device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    request = rf.get("/", HTTP_X_DEVICE_TOKEN=token, HTTP_AUTHORIZATION=f"Bearer {jwt}")
    p = resolve_principal(request)
    assert p is not None
    assert (p.kind, p.actor_id, p.actor_role, p.device_id) == ("STAFF", waiter.id, "WAITER", dev.id)


@pytest.mark.django_db
def test_staff_token_on_another_device_is_rejected(restaurant, waiter, device) -> None:
    dev, token = device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=uuid7()
    )
    with pytest.raises(AuthError, match="different device"):
        resolve_principal(
            rf.get("/", HTTP_X_DEVICE_TOKEN=token, HTTP_AUTHORIZATION=f"Bearer {jwt}")
        )


@pytest.mark.django_db
def test_revoked_device_is_rejected(restaurant, waiter, device) -> None:
    dev, token = device
    Device.objects.filter(pk=dev.pk).update(revoked_at=timezone.now())
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    with pytest.raises(AuthError) as err:
        resolve_principal(
            rf.get("/", HTTP_X_DEVICE_TOKEN=token, HTTP_AUTHORIZATION=f"Bearer {jwt}")
        )
    assert err.value.code == "device_revoked"


@pytest.mark.django_db
def test_unknown_device_is_rejected(restaurant) -> None:
    with pytest.raises(AuthError) as err:
        resolve_principal(rf.get("/", HTTP_X_DEVICE_TOKEN="nope"))
    assert err.value.code == "device_unknown"


@pytest.mark.django_db
def test_guest_token_is_scoped_to_its_session(restaurant) -> None:
    sid = uuid7()
    jwt = issue_guest_token(session_id=sid, restaurant_id=restaurant.id, mode="qr")
    p = resolve_principal(rf.get("/", HTTP_AUTHORIZATION=f"Bearer {jwt}"))
    assert p is not None
    assert (p.kind, p.actor_id, p.actor_role, p.session_id) == ("GUEST", None, "GUEST", sid)


@pytest.mark.django_db
def test_garbage_bearer_is_rejected(restaurant) -> None:
    with pytest.raises(AuthError) as err:
        resolve_principal(rf.get("/", HTTP_AUTHORIZATION="Bearer not.a.jwt"))
    assert err.value.code == "token_invalid"
