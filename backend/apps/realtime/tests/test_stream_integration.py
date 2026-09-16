"""
WS04 exit tests against a real Redis and real commits: run_command → on_commit publish → stream.
Needs the Redis from infra/compose.dev.yml. Heartbeats are shortened so the generator yields often and
the tests never have to cancel it mid-await.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from asgiref.sync import sync_to_async
from django.test import AsyncRequestFactory, RequestFactory
from django.utils import timezone

from apps.accounts.models import Device
from apps.accounts.tokens import issue_staff_token
from apps.core.commands import CommandOutcome, EventDraft, run_command
from apps.core.roles import AggregateType
from apps.core.uuid7 import uuid7
from apps.orders.events import EventType
from apps.realtime import metrics
from apps.realtime.stream import event_stream
from apps.realtime.views import EventsView, stream


@pytest.fixture(autouse=True)
def fast_stream(settings: Any) -> None:
    settings.SSE_HEARTBEAT_SECONDS = 0.05
    settings.SSE_AUTH_RECHECK_SECONDS = 0.1


def draft(aggregate: AggregateType, event_type: EventType, **payload: Any) -> EventDraft:
    return EventDraft(aggregate, uuid7(), event_type, payload)


def emit(make_ctx: Any, *drafts: EventDraft) -> None:
    run_command(make_ctx(), lambda ctx: CommandOutcome(events=list(drafts), response={}))


def menu_event() -> EventDraft:
    return draft(AggregateType.MENU_ITEM, EventType.ITEM_86ED, name="Tilapia")


def payment_event() -> EventDraft:
    return draft(AggregateType.SESSION, EventType.PAYMENT_RECORDED, amount_pesewas=7500)


async def take(gen: AsyncIterator[str], seconds: float) -> list[str]:
    """Everything except keepalives the stream yields within `seconds`, or until it ends."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    out: list[str] = []
    while loop.time() < deadline:
        try:
            chunk = await gen.__anext__()
        except StopAsyncIteration:
            break
        if isinstance(chunk, bytes):
            chunk = chunk.decode()
        if not chunk.startswith(":"):
            out.append(chunk)
    return out


def ids(chunks: list[str]) -> list[str]:
    return [c.split("\n")[0] for c in chunks]


async def settle() -> None:
    await asyncio.sleep(0.2)  # let the subscription land before publishing


@pytest.mark.django_db(transaction=True)
def test_command_reaches_stream_then_reconnect_gets_exactly_the_gap(restaurant, make_ctx) -> None:
    emit_async = sync_to_async(emit)

    async def live() -> None:
        gen = event_stream(restaurant.id, "OWNER", since=None)
        await take(gen, 0.1)  # subscribes on first iteration
        await settle()
        await emit_async(make_ctx, menu_event())  # seq 1
        chunks = await take(gen, 0.5)
        await gen.aclose()
        assert ids(chunks) == ["id: 1"]

    asyncio.run(live())

    # Offline: two events happen while the tablet has no WiFi.
    emit(make_ctx, menu_event())  # seq 2
    emit(make_ctx, payment_event())  # seq 3

    async def reconnect() -> None:
        gen = event_stream(restaurant.id, "OWNER", since=1)
        chunks = await take(gen, 0.5)
        await gen.aclose()
        assert ids(chunks) == ["id: 2", "id: 3"]
        assert [json.loads(c.split("data: ", 1)[1])["seq"] for c in chunks] == [2, 3]

    asyncio.run(reconnect())


@pytest.mark.django_db(transaction=True)
def test_kitchen_does_not_receive_payments_cashier_does(restaurant, make_ctx) -> None:
    async def scenario() -> None:
        kitchen = event_stream(restaurant.id, "KITCHEN", since=None)
        cashier = event_stream(restaurant.id, "CASHIER", since=None)
        await asyncio.gather(take(kitchen, 0.1), take(cashier, 0.1))
        await settle()
        await sync_to_async(emit)(make_ctx, payment_event(), menu_event())  # seq 1, 2
        k, c = await asyncio.gather(take(kitchen, 0.5), take(cashier, 0.5))
        await kitchen.aclose()
        await cashier.aclose()
        assert [x.split("\n")[1] for x in k] == ["event: ITEM_86ED"]
        assert [x.split("\n")[1] for x in c] == ["event: PAYMENT_RECORDED", "event: ITEM_86ED"]

    asyncio.run(scenario())


@pytest.mark.django_db(transaction=True)
def test_restaurants_do_not_see_each_others_events(restaurant, other_restaurant, make_ctx) -> None:
    async def scenario() -> None:
        ours = event_stream(restaurant.id, "OWNER", since=None)
        theirs = event_stream(other_restaurant.id, "OWNER", since=None)
        await asyncio.gather(take(ours, 0.1), take(theirs, 0.1))
        await settle()
        await sync_to_async(emit)(make_ctx, menu_event())
        a, b = await asyncio.gather(take(ours, 0.5), take(theirs, 0.5))
        await ours.aclose()
        await theirs.aclose()
        assert ids(a) == ["id: 1"]
        assert b == []

    asyncio.run(scenario())

    async def replay_other() -> None:
        gen = event_stream(other_restaurant.id, "OWNER", since=0)
        chunks = await take(gen, 0.3)
        await gen.aclose()
        assert chunks == []

    asyncio.run(replay_other())


@pytest.mark.django_db(transaction=True)
def test_polling_returns_the_same_envelopes_as_the_stream(restaurant, principal, make_ctx) -> None:
    emit(make_ctx, menu_event(), payment_event())
    emit(make_ctx, menu_event())

    async def from_stream() -> list[dict[str, Any]]:
        gen = event_stream(restaurant.id, "WAITER", since=0)
        chunks = await take(gen, 0.4)
        await gen.aclose()
        return [json.loads(c.split("data: ", 1)[1]) for c in chunks]

    streamed = asyncio.run(from_stream())

    request = RequestFactory().get("/api/v1/events?since=0")
    request.principal = principal
    request.auth_error = None
    polled = EventsView.as_view()(request).data["events"]

    assert [e["seq"] for e in streamed] == [1, 2, 3]
    assert json.loads(json.dumps(polled, default=str)) == streamed


@pytest.mark.django_db
def test_polling_advances_past_events_the_role_cannot_see(restaurant, make_ctx) -> None:
    """A kitchen poller must not loop forever on a run of payments it is not allowed to see."""
    from apps.accounts.principals import Principal
    from apps.core.roles import ActorRole

    emit(make_ctx, payment_event())
    emit(make_ctx, payment_event())
    kitchen = Principal("STAFF", restaurant.id, None, ActorRole.KITCHEN, None)

    request = RequestFactory().get("/api/v1/events?since=0&limit=1")
    request.principal = kitchen
    request.auth_error = None
    first = EventsView.as_view()(request).data
    assert first == {"events": [], "last_seq": 1, "has_more": True}

    request = RequestFactory().get("/api/v1/events?since=1&limit=1")
    request.principal = kitchen
    request.auth_error = None
    assert EventsView.as_view()(request).data == {"events": [], "last_seq": 2, "has_more": False}


@pytest.mark.django_db(transaction=True)
def test_gap_longer_than_one_batch_sends_resync_at_head(restaurant, make_ctx, settings) -> None:
    settings.SSE_REPLAY_LIMIT = 2
    for _ in range(3):
        emit(make_ctx, menu_event())  # seq 1..3

    async def scenario() -> None:
        gen = event_stream(restaurant.id, "OWNER", since=0)
        first = await take(gen, 0.2)
        assert first == ['id: 3\nevent: RESYNC\ndata: {"seq": 3}\n\n']
        await settle()
        await sync_to_async(emit)(make_ctx, menu_event())  # seq 4 arrives live after the resync
        live = await take(gen, 0.5)
        await gen.aclose()
        assert ids(live) == ["id: 4"]

    asyncio.run(scenario())


@pytest.mark.django_db(transaction=True)
def test_stream_connect_touches_device_last_seen_at(restaurant, waiter, device) -> None:
    """WS04 §4: connect updates last_seen_at (throttled in accounts._touch_device to once/min)."""
    dev, token = device
    Device.objects.unscoped().filter(pk=dev.pk).update(last_seen_at=None)
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    request = AsyncRequestFactory().get(
        "/api/v1/stream", headers={"X-Device-Token": token, "Authorization": f"Bearer {jwt}"}
    )

    async def scenario() -> None:
        response = await stream(request)
        assert response.status_code == 200
        body = response.streaming_content.__aiter__()  # type: ignore[union-attr]
        await take(body, 0.2)
        await body.aclose()

    asyncio.run(scenario())
    refreshed = Device.objects.unscoped().get(pk=dev.pk)
    assert refreshed.last_seen_at is not None


@pytest.mark.django_db(transaction=True)
def test_revoked_device_mid_stream_gets_auth_expired_and_eof(restaurant, waiter, device) -> None:
    dev, token = device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    request = AsyncRequestFactory().get(
        "/api/v1/stream", headers={"X-Device-Token": token, "Authorization": f"Bearer {jwt}"}
    )

    def revoke() -> None:
        Device.objects.unscoped().filter(pk=dev.pk).update(revoked_at=timezone.now())

    async def scenario() -> None:
        response = await stream(request)
        assert response.status_code == 200
        body = response.streaming_content.__aiter__()  # type: ignore[union-attr]
        assert await take(body, 0.3) == []  # healthy: keepalives only
        await sync_to_async(revoke)()
        chunks = await take(body, 1.0)
        assert len(chunks) == 1 and chunks[0].startswith("event: AUTH_EXPIRED\n")
        with pytest.raises(StopAsyncIteration):
            await body.__anext__()

    asyncio.run(scenario())


@pytest.mark.django_db(transaction=True)
def test_connection_gauge_counts_open_streams(restaurant) -> None:
    async def scenario() -> None:
        assert metrics.connection_count(restaurant.id, "KITCHEN") == 0
        gen = event_stream(restaurant.id, "KITCHEN", since=None)
        await take(gen, 0.1)
        assert metrics.connection_count(restaurant.id, "KITCHEN") == 1
        assert f'stream_connections{{restaurant="{restaurant.id}",role="KITCHEN"}} 1' in (
            metrics.render()
        )
        await gen.aclose()
        assert metrics.connection_count(restaurant.id, "KITCHEN") == 0

    asyncio.run(scenario())


def test_metrics_endpoint_is_hidden_without_token(client, settings) -> None:
    settings.METRICS_TOKEN = ""
    settings.DEBUG = False
    assert client.get("/metrics").status_code == 404
    settings.METRICS_TOKEN = "s3cret"
    assert client.get("/metrics").status_code == 404
    ok = client.get("/metrics", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200
    assert b"# TYPE stream_connections gauge" in ok.content
