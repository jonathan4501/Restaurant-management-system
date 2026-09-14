"""WS01: device enrolment, PIN login, authorisation, guest tokens, owner TOTP."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.accounts.enrolment import assign_enrolment_code, normalize_enrolment_code
from apps.accounts.models import Device, Staff
from apps.accounts.pin_lockout import clear_failures
from apps.accounts.pins import hash_pin
from apps.accounts.tokens import issue_staff_token, new_device_token
from apps.core.publisher import client as redis_client
from apps.core.roles import AuthorisationPurpose
from apps.core.uuid7 import uuid7
from apps.floor.models import Table, TableSession
from apps.orders.models import OrderEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def _clean_redis_and_cache() -> None:
    cache.clear()
    try:
        redis_client().flushdb()
    except Exception:
        pass


def _key() -> str:
    return str(uuid7())


def _headers(device_token: str | None = None, jwt: str | None = None) -> dict[str, str]:
    h = {"HTTP_IDEMPOTENCY_KEY": _key()}
    if device_token:
        h["HTTP_X_DEVICE_TOKEN"] = device_token
    if jwt:
        h["HTTP_AUTHORIZATION"] = f"Bearer {jwt}"
    return h


@pytest.fixture
def pending_device(restaurant) -> Device:
    return Device.objects.create(
        label="Pending tablet",
        allowed_roles=["WAITER", "CASHIER"],
        enrolment_code=normalize_enrolment_code("ABCD-1234"),
        enrolment_expires_at=timezone.now() + timedelta(minutes=15),
    )


def test_enrol_returns_token_and_emits_event(api, restaurant, pending_device) -> None:
    response = api.post(
        "/api/v1/devices/enrol",
        {"enrolment_code": "ABCD-1234"},
        format="json",
        **_headers(),
    )
    assert response.status_code == 200, response.data
    assert "device_token" in response.data
    assert response.data["device_id"] == str(pending_device.id)

    pending_device.refresh_from_db()
    assert pending_device.token_hash is not None
    assert pending_device.enrolment_code is None
    assert OrderEvent.objects.filter(event_type="DEVICE_ENROLLED").exists()


def test_enrol_token_works_on_devices_me(api, restaurant, pending_device, waiter) -> None:
    enrolled = api.post(
        "/api/v1/devices/enrol",
        {"enrolment_code": "ABCD-1234"},
        format="json",
        **_headers(),
    )
    assert enrolled.status_code == 200
    token = enrolled.data["device_token"]
    device = Device.objects.get(pk=pending_device.pk)
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=device.id
    )
    me = api.get(
        "/api/v1/devices/me",
        HTTP_X_DEVICE_TOKEN=token,
        HTTP_AUTHORIZATION=f"Bearer {jwt}",
    )
    assert me.status_code == 200
    assert me.data["label"] == "Pending tablet"
    assert any(s["id"] == str(waiter.id) for s in me.data["staff"])


def test_revoked_device_is_401(api, restaurant, device, waiter) -> None:
    dev, token = device
    Device.objects.filter(pk=dev.pk).update(revoked_at=timezone.now())
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    response = api.get(
        "/api/v1/devices/me",
        HTTP_X_DEVICE_TOKEN=token,
        HTTP_AUTHORIZATION=f"Bearer {jwt}",
    )
    assert response.status_code == 401
    assert response.data["code"] == "device_revoked"


def test_expired_enrolment_code_is_400(api, restaurant) -> None:
    Device.objects.create(
        label="Expired",
        allowed_roles=["WAITER"],
        enrolment_code=normalize_enrolment_code("ZZZZ-9999"),
        enrolment_expires_at=timezone.now() - timedelta(minutes=1),
    )
    response = api.post(
        "/api/v1/devices/enrol",
        {"enrolment_code": "ZZZZ-9999"},
        format="json",
        **_headers(),
    )
    assert response.status_code == 400


def test_pin_lockout_after_five_failures(api, restaurant, device, waiter) -> None:
    dev, token = device
    clear_failures(dev.id)

    for i in range(4):
        response = api.post(
            "/api/v1/auth/pin",
            {"staff_id": str(waiter.id), "pin": "0000"},
            format="json",
            HTTP_X_DEVICE_TOKEN=token,
            HTTP_IDEMPOTENCY_KEY=_key(),
        )
        assert response.status_code == 401, (i, response.data)
        assert response.data["code"] == "pin_invalid"
        assert OrderEvent.objects.filter(event_type="PIN_FAILED").count() == i + 1

    fifth = api.post(
        "/api/v1/auth/pin",
        {"staff_id": str(waiter.id), "pin": "0000"},
        format="json",
        HTTP_X_DEVICE_TOKEN=token,
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert fifth.status_code == 423
    assert fifth.data["code"] == "pin_locked"
    assert "retry_after_seconds" in fifth.data
    assert OrderEvent.objects.filter(event_type="PIN_LOCKED").exists()

    # Still locked even with the correct PIN.
    locked = api.post(
        "/api/v1/auth/pin",
        {"staff_id": str(waiter.id), "pin": "1234"},
        format="json",
        HTTP_X_DEVICE_TOKEN=token,
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert locked.status_code == 423

    # After lockout expiry, correct PIN works.
    redis_client().delete(f"pin_fail:{dev.id}")
    ok = api.post(
        "/api/v1/auth/pin",
        {"staff_id": str(waiter.id), "pin": "1234"},
        format="json",
        HTTP_X_DEVICE_TOKEN=token,
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert ok.status_code == 200, ok.data
    assert "token" in ok.data
    assert ok.data["staff"]["id"] == str(waiter.id)


def test_jwt_from_device_a_rejected_on_device_b(api, restaurant, waiter) -> None:
    a_token, a_hash = new_device_token()
    b_token, b_hash = new_device_token()
    device_a = Device.objects.create(
        label="A", token_hash=a_hash, allowed_roles=["WAITER"], enrolled_at=timezone.now()
    )
    Device.objects.create(
        label="B", token_hash=b_hash, allowed_roles=["WAITER"], enrolled_at=timezone.now()
    )
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=device_a.id
    )
    response = api.get(
        "/api/v1/devices/me",
        HTTP_X_DEVICE_TOKEN=b_token,
        HTTP_AUTHORIZATION=f"Bearer {jwt}",
    )
    assert response.status_code == 401
    assert response.data["code"] == "token_invalid"


def test_authorisation_single_use_purpose_and_expiry(
    api, restaurant, device, waiter, manager
) -> None:
    from apps.accounts.authorisation import consume_authorisation, issue_authorisation

    dev, token = device
    staff_jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )

    auth = api.post(
        "/api/v1/auth/authorise",
        {"pin": "1234", "purpose": AuthorisationPurpose.DISCOUNT},
        format="json",
        HTTP_X_DEVICE_TOKEN=token,
        HTTP_AUTHORIZATION=f"Bearer {staff_jwt}",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert auth.status_code == 200, auth.data
    assert auth.data["expires_in"] == 60
    assert OrderEvent.objects.filter(event_type="MANAGER_AUTHORISED").exists()

    at = auth.data["authorisation_token"]
    consume_authorisation(at, device_id=dev.id, purpose=AuthorisationPurpose.DISCOUNT)
    with pytest.raises(Exception) as err:
        consume_authorisation(at, device_id=dev.id, purpose=AuthorisationPurpose.DISCOUNT)
    assert err.value.code == "authorisation_invalid"  # type: ignore[attr-defined]

    wrong_purpose = issue_authorisation(
        staff_id=manager.id, device_id=dev.id, purpose=AuthorisationPurpose.COMP
    )
    with pytest.raises(Exception) as err2:
        consume_authorisation(
            wrong_purpose, device_id=dev.id, purpose=AuthorisationPurpose.DISCOUNT
        )
    assert err2.value.code == "authorisation_purpose_mismatch"  # type: ignore[attr-defined]

    expired = issue_authorisation(
        staff_id=manager.id, device_id=dev.id, purpose=AuthorisationPurpose.DISCOUNT
    )
    redis_client().delete(f"auth:{expired}")
    with pytest.raises(Exception) as err3:
        consume_authorisation(expired, device_id=dev.id, purpose=AuthorisationPurpose.DISCOUNT)
    assert err3.value.code == "authorisation_invalid"  # type: ignore[attr-defined]


def _open_session(restaurant, waiter, table: Table | None = None) -> TableSession:
    if table is None:
        table = Table.objects.create(number="7", qr_token=Table.new_qr_token())
    return TableSession.objects.create(
        table=table,
        opened_by=waiter,
        opened_at=timezone.now(),
        bill_total_pesewas=0,
        paid_pesewas=0,
    )


def test_guest_token_sandbox_and_throttle(api, restaurant, device, waiter) -> None:
    dev, dtoken = device
    session = _open_session(restaurant, waiter)
    other = _open_session(
        restaurant, waiter, Table.objects.create(number="8", qr_token=Table.new_qr_token())
    )
    staff_jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )

    issued = api.post(
        f"/api/v1/sessions/{session.id}/guest-token",
        {"mode": "guest"},
        format="json",
        HTTP_X_DEVICE_TOKEN=dtoken,
        HTTP_AUTHORIZATION=f"Bearer {staff_jwt}",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert issued.status_code == 200, issued.data
    guest_jwt = issued.data["token"]

    # Own session OK.
    own = api.get(
        f"/api/v1/guest/sessions/{session.id}",
        HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
    )
    assert own.status_code == 200
    assert own.data["id"] == str(session.id)

    # Another session → 404 (not 403).
    other_resp = api.get(
        f"/api/v1/guest/sessions/{other.id}",
        HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
    )
    assert other_resp.status_code == 404

    # Staff route → 403.
    staff_route = api.get(
        "/api/v1/devices/me",
        HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
    )
    assert staff_route.status_code == 403
    assert staff_route.data["code"] == "role_not_allowed"

    # Throttle at 61/min.
    cache.clear()
    statuses = []
    for _ in range(61):
        r = api.get(
            f"/api/v1/guest/sessions/{session.id}",
            HTTP_AUTHORIZATION=f"Bearer {guest_jwt}",
        )
        statuses.append(r.status_code)
    assert 429 in statuses
    assert statuses.count(200) == 60


def test_owner_api_without_totp_is_401(api, restaurant) -> None:
    User = get_user_model()
    user = User.objects.create_user(
        username="owner@test.gh", email="owner@test.gh", password="a-long-enough-password"
    )
    Staff.objects.create(
        full_name="Owner",
        role="OWNER",
        pin_hash=hash_pin("1234"),
        email="owner@test.gh",
        user=user,
    )
    TOTPDevice.objects.create(user=user, name="default", confirmed=True)

    login = api.post(
        "/api/v1/auth/owner/login",
        {"email": "owner@test.gh", "password": "a-long-enough-password"},
        format="json",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert login.status_code == 200
    assert login.data["totp_required"] is True

    me = api.get("/api/v1/auth/owner/me")
    assert me.status_code == 401


def test_owner_totp_unlocks_owner_me(api, restaurant) -> None:
    User = get_user_model()
    user = User.objects.create_user(
        username="owner2@test.gh", email="owner2@test.gh", password="a-long-enough-password"
    )
    Staff.objects.create(
        full_name="Owner Two",
        role="OWNER",
        pin_hash=hash_pin("1234"),
        email="owner2@test.gh",
        user=user,
    )
    device = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    code = f"{totp(device.bin_key):06d}"

    assert (
        api.post(
            "/api/v1/auth/owner/login",
            {"email": "owner2@test.gh", "password": "a-long-enough-password"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=_key(),
        ).status_code
        == 200
    )
    totp_resp = api.post(
        "/api/v1/auth/owner/totp",
        {"code": code},
        format="json",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert totp_resp.status_code == 200, totp_resp.data
    # Session must carry the OTP device for the next request.
    assert any("otp" in k for k in api.cookies.keys()) or "sessionid" in api.cookies
    me = api.get("/api/v1/auth/owner/me")
    assert me.status_code == 200, (me.data, dict(api.cookies), list(api.session.keys()))
    assert me.data["email"] == "owner2@test.gh"


def test_logout_revokes_staff_jwt(api, restaurant, device, waiter) -> None:
    dev, dtoken = device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    assert (
        api.get(
            "/api/v1/devices/me",
            HTTP_X_DEVICE_TOKEN=dtoken,
            HTTP_AUTHORIZATION=f"Bearer {jwt}",
        ).status_code
        == 200
    )
    logout = api.post(
        "/api/v1/auth/logout",
        {},
        format="json",
        HTTP_X_DEVICE_TOKEN=dtoken,
        HTTP_AUTHORIZATION=f"Bearer {jwt}",
        HTTP_IDEMPOTENCY_KEY=_key(),
    )
    assert logout.status_code == 200
    again = api.get(
        "/api/v1/devices/me",
        HTTP_X_DEVICE_TOKEN=dtoken,
        HTTP_AUTHORIZATION=f"Bearer {jwt}",
    )
    assert again.status_code == 401


def test_assign_enrolment_code_format(restaurant) -> None:
    device = Device.objects.create(label="X", allowed_roles=["WAITER"])
    code = assign_enrolment_code(device)
    assert len(normalize_enrolment_code(code)) == 8
    assert "-" in code
