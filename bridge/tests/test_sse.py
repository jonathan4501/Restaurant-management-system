"""
SSE framing.

The bridge's whole resume story rests on reading `id:` correctly, so this is where the reconnect
correctness starts. A malformed message must be skipped, not fatal: one bad event on a Friday night
must not stop every ticket after it.
"""

from __future__ import annotations

import json

from renzy_bridge.api import StreamEvent, parse_sse


def events(raw: str) -> list[StreamEvent]:
    return list(parse_sse(iter(raw.split("\n"))))


def test_one_message_carries_its_id_type_and_payload() -> None:
    (event,) = events('id: 7\nevent: ORDER_SUBMITTED\ndata: {"seq": 7}\n\n')
    assert event.event_id == "7"
    assert event.event == "ORDER_SUBMITTED"
    assert event.data == {"seq": 7}


def test_keepalive_comments_are_not_events() -> None:
    """`: keepalive` is the server proving it is alive during a quiet service."""
    assert events(": keepalive\n\n: keepalive\n\n") == []


def test_multiline_data_is_joined_before_parsing() -> None:
    (event,) = events('id: 9\nevent: X\ndata: {"a":\ndata:  1}\n\n')
    assert event.data == {"a": 1}


def test_a_message_with_unparseable_json_is_skipped_not_fatal() -> None:
    parsed = events('id: 1\nevent: A\ndata: not json\n\nid: 2\nevent: B\ndata: {"ok": true}\n\n')
    assert [(e.event, e.event_id, e.data) for e in parsed] == [
        ("A", "1", {}),
        ("B", "2", {"ok": True}),
    ]


def test_a_non_object_payload_is_wrapped_rather_than_dropped() -> None:
    (event,) = events("id: 3\nevent: A\ndata: 42\n\n")
    assert event.data == {"value": 42}


def test_carriage_returns_from_the_wire_are_stripped() -> None:
    (event,) = events('id: 4\r\nevent: ORDER_SUBMITTED\r\ndata: {"seq": 4}\r\n\r\n')
    assert event.event_id == "4"
    assert event.data == {"seq": 4}


def test_an_unterminated_trailing_message_is_not_emitted() -> None:
    """Half a message means the connection dropped mid-write; the cursor must not advance past it."""
    assert events('id: 5\nevent: A\ndata: {"seq": 5}') == []


def test_control_events_are_recognised_as_control() -> None:
    (resync,) = events('event: RESYNC\ndata: {"seq": 900}\n\n')
    (expired,) = events('event: AUTH_EXPIRED\ndata: {"detail": "Sign in again."}\n\n')
    (normal,) = events('id: 1\nevent: ORDER_SUBMITTED\ndata: {"seq": 1}\n\n')
    assert resync.is_control and expired.is_control
    assert not normal.is_control


def test_parses_what_the_server_actually_writes() -> None:
    """
    The exact string shape of apps.realtime.stream.format_sse. If that changes, this fails here
    rather than on a Pi in Accra.
    """
    envelope = {
        "id": "0192f5aa-0000-7000-8000-00000000abcd",
        "seq": 412,
        "type": "ORDER_SUBMITTED",
        "aggregate_type": "ORDER",
    }
    wire = f"id: {envelope['seq']}\nevent: {envelope['type']}\ndata: {json.dumps(envelope)}\n\n"
    (event,) = events(wire)
    assert event.event_id == "412"
    assert event.data["id"] == envelope["id"]
