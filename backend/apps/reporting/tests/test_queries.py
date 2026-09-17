"""
Reporting unit tests: the behaviours WS06 lists as required, independent of the service script.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.utils import timezone

from apps.accounts.models import Staff
from apps.core.roles import ActorRole, AggregateType
from apps.core.uuid7 import uuid7
from apps.floor.models import Table, TableSession
from apps.orders.events import EventType, is_flagged
from apps.orders.models import Order, OrderEvent, OrderStatus
from apps.payments.models import Payment, PaymentMethod, Shift
from apps.reporting.models import DailySales
from apps.reporting.queries import event_log, order_number_gaps, variance
from apps.reporting.rollup import rollup_daily_sales
from apps.reporting.summary import render_summary, send_summary
from apps.reporting.windows import current_business_date, day_bounds


def _event(
    *,
    seq: int,
    event_type: str,
    payload: dict,
    actor: Staff | None = None,
    authorised_by: Staff | None = None,
    reason_code: str | None = None,
    created_at: datetime | None = None,
    order_id=None,
) -> OrderEvent:
    return OrderEvent.objects.create(
        seq=seq,
        aggregate_type=AggregateType.ORDER,
        aggregate_id=order_id or uuid7(),
        order_id=order_id,
        event_type=event_type,
        payload=payload,
        actor=actor,
        actor_role=ActorRole.WAITER if actor else ActorRole.SYSTEM,
        authorised_by=authorised_by,
        reason_code=reason_code,
        idempotency_key=uuid7(),
        client_created_at=created_at or timezone.now(),
        created_at=created_at or timezone.now(),
    )


def _session(waiter: Staff, table: Table) -> TableSession:
    return TableSession.objects.create(
        table=table,
        opened_by=waiter,
        party_size=2,
        opened_at=timezone.now(),
        bill_total_pesewas=0,
        paid_pesewas=0,
    )


def _order(session: TableSession, number: int, day: date) -> Order:
    return Order.objects.create(
        session=session,
        business_date=day,
        order_number=number,
        status=OrderStatus.CLOSED,
        created_at=timezone.now(),
    )


@pytest.mark.django_db
def test_order_number_gaps_detect_missing_ticket(restaurant, waiter):
    table = Table.objects.create(number="1", qr_token=Table.new_qr_token())
    session = _session(waiter, table)
    day = date(2026, 9, 16)
    for n in (1, 2, 4):
        _order(session, n, day)
    assert order_number_gaps(day) == [3]


@pytest.mark.django_db
def test_void_before_ack_is_not_variance_void_after_ack_is(restaurant, waiter, manager):
    """A pull before the kitchen started is housekeeping; after it, food was cooked."""
    start = timezone.now() - timedelta(hours=2)
    day = current_business_date(restaurant)

    before = _event(
        seq=1,
        event_type=EventType.ORDER_VOIDED,
        payload={"status_at_void": "SUBMITTED", "total_pesewas": 3600, "order_number": 1},
        actor=waiter,
        reason_code="CUSTOMER_LEFT",
        created_at=start + timedelta(minutes=5),
    )
    after = _event(
        seq=2,
        event_type=EventType.ORDER_VOIDED,
        payload={"status_at_void": "PREPARING", "total_pesewas": 5000, "order_number": 2},
        actor=waiter,
        authorised_by=manager,
        reason_code="WRONG_ITEM",
        created_at=start + timedelta(minutes=10),
    )
    assert not is_flagged(before.event_type, before.payload)
    assert is_flagged(after.event_type, after.payload)

    report = variance(restaurant, day, day)
    voids = report["voids_after_acknowledgement"]
    assert len(voids) == 1
    assert voids[0]["value_pesewas"] == 5000
    assert voids[0]["actor"] == waiter.full_name
    assert voids[0]["authorised_by"] == manager.full_name
    assert report["void_value_pesewas"] == 5000


@pytest.mark.django_db
def test_business_date_0230_belongs_to_previous_service(restaurant):
    """Cutover defaults to 04:00 Africa/Accra — 02:30 is still yesterday's service."""
    local = datetime(2026, 9, 17, 2, 30, tzinfo=ZoneInfo(restaurant.timezone))
    assert current_business_date(restaurant, at=local.astimezone(UTC)) == date(2026, 9, 16)
    start, end = day_bounds(restaurant, date(2026, 9, 16))
    assert start <= local < end


@pytest.mark.django_db
def test_event_log_flagged_and_cursor_pages_do_not_overlap(restaurant, waiter, manager):
    base = timezone.now()
    _event(
        seq=1,
        event_type=EventType.ORDER_SERVED,
        payload={},
        actor=waiter,
        created_at=base,
    )
    _event(
        seq=2,
        event_type=EventType.DISCOUNT_APPLIED,
        payload={"amount_pesewas": 4500},
        actor=manager,
        authorised_by=manager,
        created_at=base + timedelta(seconds=1),
    )
    _event(
        seq=3,
        event_type=EventType.ORDER_SERVED,
        payload={},
        actor=waiter,
        created_at=base + timedelta(seconds=2),
    )
    _event(
        seq=4,
        event_type=EventType.COMP_APPLIED,
        payload={"amount_pesewas": 5000},
        actor=manager,
        authorised_by=manager,
        created_at=base + timedelta(seconds=3),
    )

    page1 = event_log(limit=2)
    assert [e["seq"] for e in page1["events"]] == [4, 3]
    assert page1["has_more"] is True
    assert page1["next_cursor"] == 3

    page2 = event_log(cursor=page1["next_cursor"], limit=2)
    assert [e["seq"] for e in page2["events"]] == [2, 1]
    assert {e["seq"] for e in page1["events"]} & {e["seq"] for e in page2["events"]} == set()

    by_type = {e["type"]: e["flagged"] for e in event_log(limit=10)["events"]}
    assert by_type[EventType.DISCOUNT_APPLIED] is True
    assert by_type[EventType.ORDER_SERVED] is False


@pytest.mark.django_db
def test_rollup_twice_idempotent(restaurant, waiter, manager):
    day = current_business_date(restaurant)
    start, _ = day_bounds(restaurant, day)
    table = Table.objects.create(number="7", qr_token=Table.new_qr_token())
    session = TableSession.objects.create(
        table=table,
        opened_by=waiter,
        party_size=3,
        opened_at=start + timedelta(hours=1),
        settled_at=start + timedelta(hours=2),
        bill_total_pesewas=10000,
        paid_pesewas=10000,
    )
    Order.objects.create(
        session=session,
        business_date=day,
        order_number=1,
        status=OrderStatus.CLOSED,
        total_pesewas=10000,
        created_at=start + timedelta(hours=1),
    )
    shift = Shift.objects.create(
        cashier=manager,
        opened_at=start,
        closed_at=start + timedelta(hours=3),
        opening_float_pesewas=0,
        expected_cash_pesewas=10000,
        declared_cash_pesewas=9800,
    )
    Payment.objects.create(
        session=session,
        shift=shift,
        method=PaymentMethod.CASH,
        amount_pesewas=10000,
        recorded_by=manager,
        recorded_at=start + timedelta(hours=2),
    )

    first = rollup_daily_sales(restaurant, day)
    second = rollup_daily_sales(restaurant, day)
    assert DailySales.objects.filter(business_date=day).count() == 1
    assert first.id == second.id
    assert first.money_taken_pesewas == second.money_taken_pesewas == 10000
    assert first.covers == second.covers == 3
    assert first.cash_variance_pesewas == second.cash_variance_pesewas == -200


@pytest.mark.django_db
def test_daily_summary_email_renders(restaurant, waiter, manager, settings):
    settings.OWNER_ALERT_EMAIL = "owner@renzy.test"
    day = current_business_date(restaurant)
    start, _ = day_bounds(restaurant, day)
    table = Table.objects.create(number="8", qr_token=Table.new_qr_token())
    session = TableSession.objects.create(
        table=table,
        opened_by=waiter,
        party_size=2,
        opened_at=start + timedelta(hours=1),
        settled_at=start + timedelta(hours=2),
        bill_total_pesewas=7500,
        paid_pesewas=7500,
    )
    shift = Shift.objects.create(
        cashier=manager,
        opened_at=start,
        closed_at=start + timedelta(hours=3),
        opening_float_pesewas=0,
        expected_cash_pesewas=7500,
        declared_cash_pesewas=7500,
    )
    Payment.objects.create(
        session=session,
        shift=shift,
        method=PaymentMethod.CASH,
        amount_pesewas=7500,
        recorded_by=manager,
        recorded_at=start + timedelta(hours=2),
    )
    row = rollup_daily_sales(restaurant, day)
    summary = render_summary(restaurant, row)
    assert "Money taken" in summary.body
    assert "Revenue" not in summary.body
    assert "Profit" not in summary.body
    assert send_summary(restaurant, row) is True
    assert len(mail.outbox) == 1
    assert "Money taken" in mail.outbox[0].body
