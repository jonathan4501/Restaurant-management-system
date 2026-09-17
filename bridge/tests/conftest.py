"""
Shared fixtures: a config with no real printers, a store on tmp_path, and two fakes.

`FakePrinter` is a real TCP server on a real loopback port, because "the printer is switched off"
is an OSError from the socket layer and mocking it away would test nothing. `FakeApi` stands in for
ApiClient and records what it was asked for, so the reconnect assertions can look at the
Last-Event-ID the bridge actually sent.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from renzy_bridge.api import ApiUnavailable, StreamEvent
from renzy_bridge.config import Config, from_dict
from renzy_bridge.store import Store

# The four goldens rendered and asserted byte-for-byte by
# backend/apps/printing/tests/test_render.py. The bridge reuses them rather than regenerating
# them: its job is to carry those exact bytes to a socket unchanged.
GOLDENS = (
    Path(__file__).resolve().parents[2] / "backend" / "apps" / "printing" / "tests" / "goldens"
)


def golden(name: str) -> bytes:
    path = GOLDENS / name
    assert path.exists(), f"missing golden {path}; it is produced by the backend printing tests"
    return path.read_bytes()


# ------------------------------------------------------------------ fake printer


class FakePrinter:
    """
    A TCP server that accepts one connection at a time and keeps every byte it was sent.

    A connection that carried nothing is not recorded: that is `printer.probe()` asking whether the
    printer is switched on, and the healthcheck does it once a minute. Only paper counts.
    """

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.host, self.port = self._sock.getsockname()
        self.received: list[bytes] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                connection, _ = self._sock.accept()
            except OSError:
                return
            with connection:
                chunks: list[bytes] = []
                while True:
                    try:
                        chunk = connection.recv(65536)
                    except OSError:
                        break
                    if not chunk:
                        break
                    chunks.append(chunk)
            if chunks:
                self.received.append(b"".join(chunks))

    def paper(self, count: int, timeout: float = 5.0) -> list[bytes]:
        """
        Wait for `count` print jobs to arrive, then return them.

        `send()` returns as soon as the socket accepted the bytes, which is a moment before this
        thread has finished reading them. Asserting on `received` without waiting is a flake.
        """
        deadline = time.monotonic() + timeout
        while len(self.received) < count and time.monotonic() < deadline:
            time.sleep(0.01)
        return list(self.received)

    def close(self) -> None:
        self._stop.set()
        self._sock.close()
        self._thread.join(timeout=2)


@pytest.fixture
def fake_printer() -> Iterator[FakePrinter]:
    printer = FakePrinter()
    try:
        yield printer
    finally:
        printer.close()


def dead_port() -> int:
    """A port nothing is listening on — binding and closing it hands back a free number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


# ------------------------------------------------------------------ fake API


class FakeApi:
    """
    Stands in for ApiClient.

    `batches` is a list of event lists: one per connection, so a test can say "this is what the
    server replays on the first connect, and this is what it sends after the reconnect".
    """

    def __init__(
        self,
        batches: list[list[StreamEvent]] | None = None,
        payloads: dict[str, bytes] | None = None,
    ) -> None:
        self.batches = list(batches or [])
        self.payloads = dict(payloads or {})
        self.sent_last_event_ids: list[str | None] = []
        self.fetched: list[str] = []
        self.closed = False

    def stream(self, last_event_id: str | None) -> Iterator[StreamEvent]:
        self.sent_last_event_ids.append(last_event_id)
        batch = self.batches.pop(0) if self.batches else []
        yield from batch

    def fetch_payload(self, path: str) -> bytes:
        self.fetched.append(path)
        try:
            return self.payloads[path]
        except KeyError:
            raise ApiUnavailable(f"GET {path}: no fake payload registered") from None

    def close(self) -> None:
        self.closed = True


# ------------------------------------------------------------------ config / store


def make_config(
    tmp_path: Path,
    *,
    printers: dict[str, Any] | None = None,
    stations: dict[str, str] | None = None,
    bridge: dict[str, Any] | None = None,
) -> Config:
    raw: dict[str, Any] = {
        "api": {"url": "https://api.example.test", "device_token": "tok-secret"},
        "printers": printers or {"kitchen": "127.0.0.1:9100", "front": "127.0.0.1:9101"},
        "stations": stations or {},
        "bridge": {"state_path": str(tmp_path / "state.sqlite3"), **(bridge or {})},
    }
    return from_dict(raw)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return make_config(tmp_path)


@pytest.fixture
def store(tmp_path: Path) -> Iterator[Store]:
    with Store(tmp_path / "state.sqlite3") as opened:
        yield opened
