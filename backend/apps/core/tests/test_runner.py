"""run_command: idempotency, sequencing, publishing, failure handling."""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.db import connection

from apps.core.commands import CommandOutcome, EventDraft, run_command
from apps.core.errors import ApiError, ErrorCode
from apps.core.models import IdempotencyKey
from apps.core.roles import AggregateType
from apps.core.tenancy import restaurant_context
from apps.core.uuid7 import uuid7
from apps.orders.events import EventType
from apps.orders.models import OrderEvent


def session_opened(table: str = "7") -> EventDraft:
    return EventDraft(
        AggregateType.SESSION, uuid7(), EventType.SESSION_OPENED, {"table_number": table}
    )


def ok_handler(*drafts: EventDraft, status: int = 201) -> Any:
    def handler(ctx: Any) -> CommandOutcome:
        return CommandOutcome(
            events=list(drafts), response={"ok": True, "n": len(drafts)}, status=status
        )

    return handler


@pytest.mark.django_db
def test_appends_events_with_gapless_seq_and_context(restaurant, waiter, device, make_ctx) -> None:
    ctx = make_ctx()
    result = run_command(ctx, ok_handler(session_opened("1"), session_opened("2")))
    assert (result.status, result.body, result.replayed) == (201, {"ok": True, "n": 2}, False)

    run_command(make_ctx(), ok_handler(session_opened("3")))

    events = list(OrderEvent.objects.order_by("seq"))
    assert [e.seq for e in events] == [1, 2, 3]
    first = events[0]
    assert first.actor_id == waiter.id
    assert first.actor_role == "WAITER"
    assert first.device_id == device[0].id
    assert first.idempotency_key == ctx.idempotency_key
    assert first.client_created_at == ctx.client_created_at
    assert first.created_at != ctx.client_created_at  # server time is authoritative
    assert first.aggregate_type == "SESSION"


@pytest.mark.django_db
def test_replay_returns_original_response(restaurant, make_ctx) -> None:
    key = uuid7()
    first = run_command(make_ctx(key=key, body={"a": 1}), ok_handler(session_opened()))
    again = run_command(
        make_ctx(key=key, body={"a": 1}), ok_handler(session_opened(), session_opened())
    )
    assert again.replayed is True
    assert (again.status, again.body) == (first.status, first.body)
    assert OrderEvent.objects.count() == 1  # the second handler never ran


@pytest.mark.django_db
def test_same_key_different_body_is_rejected(restaurant, make_ctx) -> None:
    key = uuid7()
    run_command(make_ctx(key=key, body={"a": 1}), ok_handler(session_opened()))
    with pytest.raises(ApiError) as err:
        run_command(make_ctx(key=key, body={"a": 2}), ok_handler(session_opened()))
    assert err.value.code == ErrorCode.IDEMPOTENCY_KEY_REUSED
    assert err.value.status_code == 422


@pytest.mark.django_db
def test_domain_rejection_is_stored_and_replayed(restaurant, make_ctx) -> None:
    key = uuid7()

    def rejecting(ctx: Any) -> CommandOutcome:
        raise ApiError(409, ErrorCode.ILLEGAL_TRANSITION, "nope")

    with pytest.raises(ApiError):
        run_command(make_ctx(key=key), rejecting)
    replay = run_command(make_ctx(key=key), ok_handler(session_opened()))
    assert replay.replayed is True
    assert replay.status == 409
    assert replay.body["code"] == "illegal_transition"
    assert OrderEvent.objects.count() == 0


@pytest.mark.django_db
def test_unexpected_failure_releases_the_key(restaurant, make_ctx) -> None:
    key = uuid7()

    def exploding(ctx: Any) -> CommandOutcome:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run_command(make_ctx(key=key), exploding)
    assert not IdempotencyKey.objects.filter(key=key).exists()
    assert OrderEvent.objects.count() == 0

    result = run_command(make_ctx(key=key), ok_handler(session_opened()))
    assert result.replayed is False
    assert OrderEvent.objects.count() == 1


@pytest.mark.django_db
def test_sequences_are_independent_per_restaurant(restaurant, other_restaurant, make_ctx) -> None:
    run_command(make_ctx(), ok_handler(session_opened(), session_opened()))
    with restaurant_context(other_restaurant.id):
        run_command(make_ctx(restaurant_id=other_restaurant.id), ok_handler(session_opened()))
        assert [e.seq for e in OrderEvent.objects.order_by("seq")] == [1]
    assert [e.seq for e in OrderEvent.objects.order_by("seq")] == [1, 2]


@pytest.mark.django_db
def test_publishes_envelopes_after_commit(
    restaurant, make_ctx, published, django_capture_on_commit_callbacks
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        run_command(make_ctx(), ok_handler(session_opened("9")))
    assert len(published) == 1
    rid, envelopes = published[0]
    assert rid == restaurant.id
    assert envelopes[0]["seq"] == 1
    assert envelopes[0]["type"] == "SESSION_OPENED"
    assert envelopes[0]["payload"] == {"table_number": "9"}
    assert envelopes[0]["actor_role"] == "WAITER"


@pytest.mark.django_db(transaction=True)
def test_concurrent_commands_get_distinct_consecutive_seq(restaurant, make_ctx) -> None:
    """Two threads, one restaurant: the advisory lock serialises appends. No duplicate seq, no gap."""
    errors: list[BaseException] = []
    start = threading.Barrier(2)

    def work() -> None:
        try:
            start.wait(timeout=5)
            with restaurant_context(restaurant.id):
                run_command(make_ctx(), ok_handler(session_opened(), session_opened()))
        except BaseException as err:  # noqa: BLE001
            errors.append(err)
        finally:
            connection.close()

    threads = [threading.Thread(target=work) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert errors == []
    assert [e.seq for e in OrderEvent.objects.order_by("seq")] == [1, 2, 3, 4]
