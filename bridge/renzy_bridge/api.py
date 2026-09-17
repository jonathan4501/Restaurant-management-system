"""
Talking to the RENZY API: the event stream in, rendered ESC/POS bytes out.

The bridge authenticates with `X-Device-Token` only. It has no staff JWT because there is no person
behind it, and the server refuses a device that was not enrolled with `allowed_roles = ['PRINTER']`.

Reconnects send `Last-Event-ID`, so the server replays what the bridge missed while the Pi was off.
Replay is what makes the queue correct rather than lucky; the store's primary key is what stops the
replay printing twice.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Config


class ApiError(RuntimeError):
    """The API answered, but not with what was asked for."""


class ApiUnavailable(RuntimeError):
    """The API could not be reached at all — the usual state during an Accra power cut."""


@dataclass(frozen=True)
class StreamEvent:
    """One SSE message. `event_id` is the value to persist as Last-Event-ID."""

    event: str
    event_id: str | None
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_control(self) -> bool:
        """RESYNC / AUTH_EXPIRED carry no envelope — they tell the client what to do next."""
        return self.event in ("RESYNC", "AUTH_EXPIRED")


class ApiClient:
    def __init__(self, config: Config, client: httpx.Client | None = None) -> None:
        self._config = config
        self._client = client or httpx.Client(
            base_url=config.api_url,
            headers={"X-Device-Token": config.device_token},
            timeout=httpx.Timeout(10.0, read=None),
        )

    def close(self) -> None:
        self._client.close()

    def fetch_payload(self, path: str) -> bytes:
        """GET the rendered ESC/POS bytes for a job."""
        try:
            response = self._client.get(path)
        except httpx.HTTPError as err:
            raise ApiUnavailable(f"GET {path}: {err}") from err
        if response.status_code == 404:
            raise ApiError(f"GET {path}: nothing to print (404)")
        if response.status_code in (401, 403):
            raise ApiError(
                f"GET {path}: device rejected ({response.status_code}). "
                "Is the Pi still enrolled with allowed_roles = ['PRINTER']?"
            )
        if response.status_code >= 400:
            raise ApiUnavailable(f"GET {path}: HTTP {response.status_code}")
        return response.content

    def stream(self, last_event_id: str | None) -> Iterator[StreamEvent]:
        """
        Yield events from `/print/stream`, resuming after `last_event_id`.

        Returns normally when the server closes the stream; the caller reconnects. Raises
        ApiUnavailable when it could not connect, which the caller treats the same way but logs
        differently.
        """
        headers = {"Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        try:
            with self._client.stream(
                "GET", "/api/v1/print/stream", headers=headers
            ) as response:
                if response.status_code in (401, 403):
                    raise ApiError(
                        f"stream refused ({response.status_code}). Enrol the Pi as a device with "
                        "allowed_roles = ['PRINTER']."
                    )
                if response.status_code >= 400:
                    raise ApiUnavailable(f"stream: HTTP {response.status_code}")
                yield from parse_sse(response.iter_lines())
        except httpx.HTTPError as err:
            raise ApiUnavailable(f"stream: {err}") from err


def parse_sse(lines: Iterator[str]) -> Iterator[StreamEvent]:
    """
    Minimal SSE framing: accumulate field lines, emit on the blank line that ends a message.

    Comment lines (`: keepalive`) are the server proving it is alive during a quiet service and are
    discarded. A message with an unparseable `data:` is skipped rather than crashing the daemon —
    one malformed event must not stop the next ticket printing.
    """
    event = "message"
    event_id: str | None = None
    data_lines: list[str] = []

    for raw in lines:
        line = raw.rstrip("\r")
        if line.startswith(":"):
            continue
        if line == "":
            if data_lines or event_id is not None:
                payload: dict[str, Any] = {}
                body = "\n".join(data_lines)
                if body:
                    try:
                        parsed = json.loads(body)
                        payload = parsed if isinstance(parsed, dict) else {"value": parsed}
                    except json.JSONDecodeError:
                        payload = {}
                yield StreamEvent(event=event, event_id=event_id, data=payload)
            event, event_id, data_lines = "message", None, []
            continue

        field_name, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field_name == "event":
            event = value
        elif field_name == "id":
            event_id = value
        elif field_name == "data":
            data_lines.append(value)
