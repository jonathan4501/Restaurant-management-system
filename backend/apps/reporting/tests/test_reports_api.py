"""
Reconcile the four owner endpoints against the WS05 service script.

Every money figure here must match `EXPECTED` from `apps.payments.tests.service_script` — that is the
hand-checkable plan the owner can add up. If a number here and a number there disagree, either the
plan moved or a report is lying.
"""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tokens import issue_staff_token
from apps.payments.tests.service_script import EXPECTED, headers, run_service_script
from apps.reporting.models import DailySales
from apps.reporting.queries import today
from apps.reporting.rollup import rollup_daily_sales
from apps.reporting.windows import current_business_date


@pytest.fixture
def service(restaurant):
    return run_service_script(restaurant)


@pytest.fixture
def owner_client(service) -> tuple[APIClient, dict[str, str]]:
    """Manager JWT on the scripted till — reports allow MANAGER and OWNER."""
    auth = service.cast.manager
    return service.cast.api, headers(auth)


@pytest.mark.django_db
def test_today_reconciles_against_expected(service, owner_client):
    api, hdrs = owner_client
    response = api.get("/api/v1/reports/today", **hdrs)
    assert response.status_code == 200
    body = response.data

    assert body["money_taken_pesewas"] == EXPECTED.money_taken_pesewas == 498500
    assert body["covers"] == EXPECTED.covers == 57
    assert body["bills_settled"] == EXPECTED.bills_settled == 18
    assert body["open_bills"] == EXPECTED.bills_open == 2
    assert body["open_balance_pesewas"] == EXPECTED.outstanding_pesewas == 47700
    assert body["average_bill_pesewas"] == EXPECTED.money_taken_pesewas // EXPECTED.bills_settled
    # Integer division only — never a float in a money path.
    assert isinstance(body["average_bill_pesewas"], int)
    assert body["average_bill_pesewas"] == 27694  # 498500 // 18


@pytest.mark.django_db
def test_patterns_reconcile_against_expected(service, owner_client):
    api, hdrs = owner_client
    day = current_business_date(service.cast.restaurant)
    response = api.get(
        "/api/v1/reports/patterns",
        {"from": str(day), "to": str(day)},
        **hdrs,
    )
    assert response.status_code == 200
    body = response.data

    assert body["money_taken_pesewas"] == EXPECTED.money_taken_pesewas
    assert body["payment_method_mix"] == EXPECTED.money_taken_by_method
    assert sum(body["payment_method_mix"].values()) == 498500

    # Best sellers are line snapshots; every name in EXPECTED's item_value map must appear, and the
    # values must add up to the same total the plan folded.
    by_name = {row["name"]: row["value_pesewas"] for row in body["best_sellers_by_value"]}
    for name, value in EXPECTED.item_value_pesewas.items():
        assert by_name[name] == value
    assert sum(by_name.values()) == sum(EXPECTED.item_value_pesewas.values())

    hourly_total = sum(row["money_taken_pesewas"] for row in body["money_taken_by_hour"])
    assert hourly_total == EXPECTED.money_taken_pesewas


@pytest.mark.django_db
def test_variance_reconciles_against_expected(service, owner_client):
    api, hdrs = owner_client
    day = current_business_date(service.cast.restaurant)
    response = api.get(
        "/api/v1/reports/variance",
        {"from": str(day), "to": str(day)},
        **hdrs,
    )
    assert response.status_code == 200
    body = response.data

    # One void after ack (WRONG_ITEM, 5000) — the cancel-before-ack must not appear.
    assert body["void_value_pesewas"] == EXPECTED.voided_orders_pesewas == 5000
    assert len(body["voids_after_acknowledgement"]) == 1
    void = body["voids_after_acknowledgement"][0]
    assert void["value_pesewas"] == 5000
    assert void["reason_code"] == "WRONG_ITEM"
    assert void["actor"]
    assert void["authorised_by"]

    assert body["discount_pesewas"] == EXPECTED.discounts_pesewas == 4500
    assert body["comp_pesewas"] == EXPECTED.comps_pesewas == 5000
    assert body["reopened_count"] == EXPECTED.sessions_reopened == 2
    assert body["manager_reopens"] == EXPECTED.manager_reopens == 1

    assert body["cash_variance_pesewas"] == sum(s.variance_pesewas for s in EXPECTED.shifts)
    assert body["cash_variance_pesewas"] == -2000
    by_cashier = {row["cashier"]: row for row in body["cash_variance_by_shift"]}
    first, second = EXPECTED.shifts
    assert by_cashier[first.cashier_name]["variance_pesewas"] == first.variance_pesewas == -2000
    assert by_cashier[second.cashier_name]["variance_pesewas"] == second.variance_pesewas == 0


@pytest.mark.django_db
def test_event_log_endpoint_pages_and_flags(service, owner_client):
    api, hdrs = owner_client
    first = api.get("/api/v1/events/log", {"limit": 25}, **hdrs)
    assert first.status_code == 200
    assert first.data["has_more"] is True
    assert first.data["next_cursor"] is not None
    seqs = [e["seq"] for e in first.data["events"]]
    assert seqs == sorted(seqs, reverse=True)

    second = api.get(
        "/api/v1/events/log",
        {"limit": 25, "cursor": first.data["next_cursor"]},
        **hdrs,
    )
    assert second.status_code == 200
    assert {e["seq"] for e in first.data["events"]} & {
        e["seq"] for e in second.data["events"]
    } == set()

    discounts = api.get("/api/v1/events/log", {"type": "DISCOUNT_APPLIED"}, **hdrs)
    assert discounts.status_code == 200
    assert discounts.data["events"]
    assert all(e["flagged"] is True for e in discounts.data["events"])

    served = api.get("/api/v1/events/log", {"type": "ORDER_SERVED", "limit": 5}, **hdrs)
    assert served.status_code == 200
    assert served.data["events"]
    assert all(e["flagged"] is False for e in served.data["events"])


@pytest.mark.django_db
def test_rollup_matches_today_and_expected(service):
    restaurant = service.cast.restaurant
    day = current_business_date(restaurant)
    live = today(restaurant)
    row = rollup_daily_sales(restaurant, day)
    again = rollup_daily_sales(restaurant, day)

    assert DailySales.objects.filter(business_date=day).count() == 1
    assert row.id == again.id
    assert row.money_taken_pesewas == live["money_taken_pesewas"] == EXPECTED.money_taken_pesewas
    assert row.covers == live["covers"] == EXPECTED.covers
    assert row.void_value_pesewas == EXPECTED.voided_orders_pesewas
    assert row.discount_pesewas == EXPECTED.discounts_pesewas + EXPECTED.comps_pesewas
    assert row.cash_variance_pesewas == sum(s.variance_pesewas for s in EXPECTED.shifts)


@pytest.mark.django_db
def test_reports_reject_waiter(service):
    waiter = service.cast.waiters[0]
    response = service.cast.api.get("/api/v1/reports/today", **headers(waiter))
    assert response.status_code == 403


@pytest.mark.django_db
def test_owner_role_can_read_today(service):
    """OWNER is the primary audience; confirm the role is wired, not only MANAGER."""
    device = service.cast.device
    device.allowed_roles = list(device.allowed_roles) + ["OWNER"]
    device.save(update_fields=["allowed_roles"])
    from apps.accounts.models import Staff
    from apps.accounts.pins import hash_pin

    owner = Staff.objects.create(
        full_name="Owner", role="OWNER", pin_hash=hash_pin("1234"), email="owner@renzy.test"
    )
    jwt = issue_staff_token(
        staff_id=owner.id,
        role="OWNER",
        restaurant_id=service.cast.restaurant.id,
        device_id=device.id,
    )
    hdrs = {
        "HTTP_X_DEVICE_TOKEN": service.cast.manager.device_token,
        "HTTP_AUTHORIZATION": f"Bearer {jwt}",
    }
    response = service.cast.api.get("/api/v1/reports/today", **hdrs)
    assert response.status_code == 200
    assert response.data["money_taken_pesewas"] == 498500
