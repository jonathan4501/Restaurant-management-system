"""
SSE: replay by Last-Event-ID, role filtering, live fan-out through a real Redis.
The live test needs the Redis from infra/compose.dev.yml (REDIS_URL in settings/test.py).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
import redis.asyncio as aioredis
from django.conf import settings
from django.test import AsyncRequestFactory, RequestFactory

from apps.accounts.tokens import issue_staff_token
from apps.core import publisher
from apps.core.commands import CommandOutcome, EventDraft, run_command
from apps.core.roles import AggregateType
from apps.core.uuid7 import uuid7
from apps.orders.events import EventType
from apps.realtime.filters import visible_to
from apps.realtime.stream import event_stream, format_sse, replay
from apps.realtime.views import EventsView, stream


def draft(aggregate: AggregateType, event_type: EventType, **payload: Any) -> EventDraft:
    return EventDraft(aggregate, uuid7(), event_type, payload)


def emit(make_ctx: Any, *drafts: EventDraft) -> None:
    run_command(make_ctx(), lambda ctx: CommandOutcome(events=list(drafts), response={}))


def test_format_sse_lines() -> None:
    text = format_sse({"seq": 7, "type": "ORDER_READY", "payload": {}})
    assert text.startswith("id: 7\nevent: ORDER_READY\ndata: ")
    assert text.endswith("\n\n")
    assert json.loads(text.split("data: ", 1)[1]) == {
        "seq": 7,
        "type": "ORDER_READY",
        "payload": {},
    }


def test_role_filter() -> None:
    order = {"aggregate_type": "ORDER"}
    payment = {"aggregate_type": "SESSION"}
    shift = {"aggregate_type": "SHIFT"}
    assert visible_to("KITCHEN", order) and not visible_to("KITCHEN", payment)
    assert visible_to("CASHIER", payment) and visible_to("CASHIER", shift)
    assert visible_to("WAITER", payment) and not visible_to("WAITER", shift)
    assert visible_to("OWNER", shift)
    assert not visible_to("GUEST", order)
    assert visible_to("PRINTER", order) and not visible_to("PRINTER", shift)


@pytest.mark.django_db
def test_replay_from_seq_with_role_filter(restaurant, make_ctx) -> None:
    emit(make_ctx, draft(AggregateType.SESSION, EventType.SESSION_OPENED, table_number="1"))
    emit(make_ctx, draft(AggregateType.MENU_ITEM, EventType.ITEM_86ED, name="Tilapia"))
    emit(make_ctx, draft(AggregateType.SESSION, EventType.PAYMENT_RECORDED, amount_pesewas=100))

    assert [e["seq"] for e in replay(restaurant.id, 0, "OWNER")] == [1, 2, 3]
    assert [e["seq"] for e in replay(restaurant.id, 1, "OWNER")] == [2, 3]
    assert [e["seq"] for e in replay(restaurant.id, 0, "KITCHEN")] == [2]
    assert replay(restaurant.id, 3, "OWNER") == []


@pytest.mark.django_db
def test_replay_is_tenant_isolated(restaurant, other_restaurant, make_ctx) -> None:
    emit(make_ctx, draft(AggregateType.SESSION, EventType.SESSION_OPENED, table_number="1"))
    assert replay(other_restaurant.id, 0, "OWNER") == []


@pytest.mark.django_db
def test_events_polling_endpoint(restaurant, principal, make_ctx) -> None:
    emit(make_ctx, draft(AggregateType.SESSION, EventType.SESSION_OPENED, table_number="1"))
    emit(make_ctx, draft(AggregateType.SESSION, EventType.SESSION_OPENED, table_number="2"))
    request = RequestFactory().get("/api/v1/events?since=1")
    request.principal = principal
    request.auth_error = None
    response = EventsView.as_view()(request)
    assert response.status_code == 200
    assert [e["seq"] for e in response.data["events"]] == [2]
    assert response.data["last_seq"] == 2


@pytest.mark.django_db
def test_stream_rejects_guests_and_anonymous(restaurant) -> None:
    request = AsyncRequestFactory().get("/api/v1/stream")
    response = asyncio.run(stream(request))
    assert response.status_code == 401
    assert response["Content-Type"] == "application/problem+json"


@pytest.mark.django_db(transaction=True)
def test_stream_accepts_a_staff_token_and_serves_event_stream(restaurant, waiter, device) -> None:
    dev, token = device
    jwt = issue_staff_token(
        staff_id=waiter.id, role="WAITER", restaurant_id=restaurant.id, device_id=dev.id
    )
    request = AsyncRequestFactory().get(
        "/api/v1/stream", headers={"X-Device-Token": token, "Authorization": f"Bearer {jwt}"}
    )
    # The generator is never iterated here, so no Redis connection is opened.
    response = asyncio.run(stream(request))
    assert response.status_code == 200, getattr(response, "content", b"")
    assert response["Content-Type"] == "text/event-stream"
    assert response["Cache-Control"] == "no-cache"


async def _collect(gen: Any, n: int, timeout: float = 5.0) -> list[str]:
    out: list[str] = []

    async def pull() -> None:
        async for chunk in gen:
            if chunk.startswith(":"):
                continue
            out.append(chunk)
            if len(out) >= n:
                break

    await asyncio.wait_for(pull(), timeout)
    await gen.aclose()
    return out


@pytest.mark.django_db(transaction=True)
def test_live_fanout_and_reconnect_replay(restaurant, make_ctx) -> None:
    """Subscribe, publish two events through Redis, receive both; reconnect with Last-Event-ID, get the gap."""
    emit(
        make_ctx, draft(AggregateType.SESSION, EventType.SESSION_OPENED, table_number="1")
    )  # seq 1

    async def scenario() -> None:
        gen = event_stream(restaurant.id, "OWNER", since=None)
        task = asyncio.create_task(_collect(gen, 2))
        await asyncio.sleep(0.3)  # let it subscribe

        r = aioredis.from_url(settings.REDIS_URL)
        for seq in (2, 3):
            env = {
                "seq": seq,
                "type": "SESSION_OPENED",
                "aggregate_type": "SESSION",
                "payload": {"table_number": str(seq)},
            }
            await r.publish(publisher.channel(restaurant.id), json.dumps(env))
        await r.aclose()

        chunks = await task
        assert [c.split("\n")[0] for c in chunks] == ["id: 2", "id: 3"]

    asyncio.run(scenario())

    # Reconnect having seen seq 0: the database replay hands back seq 1 first.
    async def reconnect() -> None:
        gen = event_stream(restaurant.id, "OWNER", since=0)
        chunks = await _collect(gen, 1)
        assert chunks[0].startswith("id: 1\nevent: SESSION_OPENED")

    asyncio.run(reconnect())
