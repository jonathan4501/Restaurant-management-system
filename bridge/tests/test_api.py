"""
The HTTP surface, against httpx's MockTransport rather than a live server.

Two things are asserted that the daemon tests cannot see from the outside: the exact headers the
bridge puts on the wire (`X-Device-Token`, and `Last-Event-ID` on a reconnect), and the split
between ApiError — the server said no and will say no again — and ApiUnavailable, which means try
later. Getting that split wrong is how a ticket is either dropped or retried forever.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from conftest import golden, make_config

from renzy_bridge.api import ApiClient, ApiError, ApiUnavailable

STREAM = "/api/v1/print/stream"


def client_for(tmp_path: Path, handler: object) -> ApiClient:
    config = make_config(tmp_path)
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return ApiClient(
        config,
        client=httpx.Client(
            base_url=config.api_url,
            headers={"X-Device-Token": config.device_token},
            transport=transport,
        ),
    )


# ------------------------------------------------------------------ fetching payloads


def test_the_rendered_bytes_come_back_untouched(tmp_path: Path) -> None:
    payload = golden("receipt.bin")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Device-Token"] == "tok-secret"
        return httpx.Response(200, content=payload)

    assert client_for(tmp_path, handler).fetch_payload("/api/v1/print/receipts/x") == payload


@pytest.mark.parametrize("status", [401, 403])
def test_a_rejected_device_is_a_permanent_error_naming_the_fix(tmp_path: Path, status: int) -> None:
    client = client_for(tmp_path, lambda request: httpx.Response(status))
    with pytest.raises(ApiError, match="allowed_roles"):
        client.fetch_payload("/api/v1/print/tickets/x")


def test_a_404_is_permanent_so_the_queue_does_not_wedge_behind_it(tmp_path: Path) -> None:
    client = client_for(tmp_path, lambda request: httpx.Response(404))
    with pytest.raises(ApiError, match="nothing to print"):
        client.fetch_payload("/api/v1/print/tickets/x")


def test_a_server_error_is_temporary_so_the_ticket_is_retried(tmp_path: Path) -> None:
    client = client_for(tmp_path, lambda request: httpx.Response(503))
    with pytest.raises(ApiUnavailable):
        client.fetch_payload("/api/v1/print/tickets/x")


def test_an_unreachable_api_is_temporary(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host", request=request)

    with pytest.raises(ApiUnavailable, match="no route to host"):
        client_for(tmp_path, handler).fetch_payload("/api/v1/print/tickets/x")


# ------------------------------------------------------------------ the stream


def sse(*messages: str) -> bytes:
    return "".join(messages).encode()


def test_a_first_connection_sends_no_last_event_id(tmp_path: Path) -> None:
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, content=sse())

    list(client_for(tmp_path, handler).stream(None))
    assert "last-event-id" not in seen[0]
    assert seen[0]["accept"] == "text/event-stream"


def test_a_reconnect_asks_the_server_to_replay_from_the_cursor(tmp_path: Path) -> None:
    """This header is the whole reason a ticket sent while the Pi was off still reaches paper."""
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        return httpx.Response(200, content=sse('id: 413\nevent: X\ndata: {"seq": 413}\n\n'))

    events = list(client_for(tmp_path, handler).stream("412"))
    assert seen[0]["last-event-id"] == "412"
    assert [e.event_id for e in events] == ["413"]


def test_the_stream_url_is_the_one_the_backend_registers(tmp_path: Path) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, content=sse())

    list(client_for(tmp_path, handler).stream(None))
    assert seen == [STREAM]


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_stream_says_how_to_enrol_the_pi(tmp_path: Path, status: int) -> None:
    client = client_for(tmp_path, lambda request: httpx.Response(status))
    with pytest.raises(ApiError, match="allowed_roles"):
        list(client.stream(None))


def test_a_stream_the_server_cannot_serve_yet_is_temporary(tmp_path: Path) -> None:
    client = client_for(tmp_path, lambda request: httpx.Response(502))
    with pytest.raises(ApiUnavailable):
        list(client.stream(None))


def test_a_dropped_connection_is_temporary(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("connection reset", request=request)

    with pytest.raises(ApiUnavailable, match="connection reset"):
        list(client_for(tmp_path, handler).stream(None))
