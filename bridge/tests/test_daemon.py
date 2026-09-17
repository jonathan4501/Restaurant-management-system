"""
The reconnect and de-duplication path, end to end, against a real socket.

WS12 names two tests: replay from disk after a restart, and printer-unreachable → queued → printed
when it comes back. Both are here, with a real TCP server rather than a mock, plus the case the
whole design exists to prevent — a reconnect that replays an event the bridge already printed must
produce no second piece of paper.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import FakeApi, FakePrinter, dead_port, golden, make_config

from renzy_bridge.api import ApiError, ApiUnavailable, StreamEvent
from renzy_bridge.config import Config
from renzy_bridge.daemon import Bridge
from renzy_bridge.store import Store

ORDER_ID = "0192f5aa-0000-7000-8000-00000000000a"
SESSION_ID = "0192f5aa-0000-7000-8000-00000000cafe"
TICKET_PATH = f"/api/v1/print/tickets/{ORDER_ID}"
RECEIPT_PATH = f"/api/v1/print/receipts/{SESSION_ID}"


def submitted_event(
    event_id: str = "0192f5aa-0000-7000-8000-00000000abcd", seq: int = 412
) -> StreamEvent:
    """An ORDER_SUBMITTED message as apps.realtime.stream.format_sse puts it on the wire."""
    return StreamEvent(
        event="ORDER_SUBMITTED",
        event_id=str(seq),
        data={
            "id": event_id,
            "seq": seq,
            "type": "ORDER_SUBMITTED",
            "aggregate_type": "ORDER",
            "aggregate_id": ORDER_ID,
            "order_id": ORDER_ID,
            "payload": {
                "order_number": 42,
                "table_number": "7",
                "lines": [{"name": "Jollof Rice", "prep_station": "KITCHEN", "quantity": 2}],
            },
        },
    )


def settled_event(
    event_id: str = "0192f5aa-0000-7000-8000-00000000beef", seq: int = 500
) -> StreamEvent:
    return StreamEvent(
        event="SESSION_SETTLED",
        event_id=str(seq),
        data={
            "id": event_id,
            "seq": seq,
            "type": "SESSION_SETTLED",
            "aggregate_type": "SESSION",
            "aggregate_id": SESSION_ID,
            "payload": {"table_number": "7"},
        },
    )


def config_for(tmp_path: Path, printer: FakePrinter) -> Config:
    return make_config(tmp_path, printers={"kitchen": f"{printer.host}:{printer.port}"})


def bridge_with(config: Config, api: Any) -> Bridge:
    return Bridge(config, Store(config.state_path), api)


class OneShotBridge(Bridge):
    """Runs the real loop, then stops after `budget` events so `run()` terminates in a test."""

    def __init__(self, *args: Any, budget: int = 1, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._budget = budget

    def handle_event(self, event: StreamEvent) -> int:
        new = super().handle_event(event)
        self._budget -= 1
        if self._budget <= 0:
            self.stop()
        return new


@pytest.fixture
def ticket_bytes() -> bytes:
    return golden("kitchen_ticket.bin")


# ------------------------------------------------------------------ the happy path


def test_a_submitted_order_reaches_the_printer_byte_for_byte(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """
    What comes off the socket must equal the golden the backend renderer is tested against. The
    bridge is a pipe; anything it does to those bytes shows up here.
    """
    api = FakeApi(payloads={TICKET_PATH: ticket_bytes})
    bridge = bridge_with(config_for(tmp_path, fake_printer), api)

    assert bridge.handle_event(submitted_event()) == 1
    assert bridge.drain() == 1

    assert fake_printer.paper(1) == [ticket_bytes]
    assert bridge.store.pending() == []


def test_the_cursor_only_moves_after_the_job_is_on_disk(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    api = FakeApi(payloads={TICKET_PATH: ticket_bytes})
    bridge = bridge_with(config_for(tmp_path, fake_printer), api)
    assert bridge.store.last_event_id() is None

    bridge.handle_event(submitted_event(seq=412))

    assert bridge.store.pending_count() == 1
    assert bridge.store.last_event_id() == "412"


# ------------------------------------------------------------ reconnect, and no double print


def test_a_replayed_event_prints_nothing_the_second_time(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """
    The reconnect guarantee. De-duplication is the store's primary key, not a timing window, so
    the replay can arrive a millisecond or an hour later and the answer is the same.
    """
    api = FakeApi(payloads={TICKET_PATH: ticket_bytes})
    bridge = bridge_with(config_for(tmp_path, fake_printer), api)

    assert bridge.handle_event(submitted_event()) == 1
    bridge.drain()
    assert bridge.handle_event(submitted_event()) == 0
    bridge.drain()

    assert fake_printer.paper(2, timeout=0.5) == [ticket_bytes]
    assert len(api.fetched) == 1


def test_a_crash_between_queueing_and_printing_still_prints_exactly_once(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """
    The dangerous window: the job is on disk, the cursor has moved, the Pi dies before the socket.
    The restart must print it, and the server's replay of the same event must not add a second.
    """
    config = config_for(tmp_path, fake_printer)
    first = bridge_with(config, FakeApi(payloads={TICKET_PATH: ticket_bytes}))
    first.handle_event(submitted_event())
    first.store.close()  # power cut, before drain

    api = FakeApi(payloads={TICKET_PATH: ticket_bytes})
    second = bridge_with(config, api)
    assert second.drain() == 1
    assert second.handle_event(submitted_event()) == 0  # the server replays it
    assert second.drain() == 0

    assert fake_printer.paper(2, timeout=0.5) == [ticket_bytes]


def test_the_stream_is_opened_with_the_stored_last_event_id(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """
    Restart-and-resume, through the real `run()` loop: the cursor on disk becomes the
    `Last-Event-ID` the server replays from, and the ticket sent while the Pi was down prints.
    """
    config = config_for(tmp_path, fake_printer)
    with Store(config.state_path) as before:
        before.set_last_event_id(412)

    api = FakeApi(batches=[[submitted_event(seq=413)]], payloads={TICKET_PATH: ticket_bytes})
    bridge = OneShotBridge(config, Store(config.state_path), api)
    bridge.run()

    assert api.sent_last_event_ids == ["412"]
    assert bridge.store.last_event_id() == "413"
    assert fake_printer.paper(1) == [ticket_bytes]


def test_a_first_ever_start_asks_for_no_replay(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """A fresh Pi must not be handed the whole history of the restaurant as paper."""
    api = FakeApi(batches=[[submitted_event()]], payloads={TICKET_PATH: ticket_bytes})
    config = config_for(tmp_path, fake_printer)
    bridge = OneShotBridge(config, Store(config.state_path), api)
    bridge.run()

    assert api.sent_last_event_ids == [None]


def test_the_loop_survives_a_stream_that_drops(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """An Accra power blip on the router: reconnect from the cursor, do not lose the queue."""

    class Flaky(FakeApi):
        def stream(self, last_event_id: str | None) -> Any:
            self.sent_last_event_ids.append(last_event_id)
            if len(self.sent_last_event_ids) == 1:
                raise ApiUnavailable("stream: connection reset")
            yield submitted_event(seq=413)

    config = make_config(
        tmp_path,
        printers={"kitchen": f"{fake_printer.host}:{fake_printer.port}"},
        bridge={"reconnect_min_seconds": 0.01, "reconnect_max_seconds": 0.01},
    )
    api = Flaky(payloads={TICKET_PATH: ticket_bytes})
    bridge = OneShotBridge(config, Store(config.state_path), api)
    bridge.run()

    assert api.sent_last_event_ids == [None, None]
    assert bridge.store.last_event_id() == "413"
    assert fake_printer.paper(1) == [ticket_bytes]


# ------------------------------------------------------------------ printer off, and back


def test_a_printer_that_is_off_queues_the_ticket_and_prints_it_on_return(
    tmp_path: Path, ticket_bytes: bytes
) -> None:
    """WS12: switch the kitchen printer off, send an order, switch it on — the ticket comes out."""
    config = make_config(tmp_path, printers={"kitchen": f"127.0.0.1:{dead_port()}"})
    api = FakeApi(payloads={TICKET_PATH: ticket_bytes})
    bridge = bridge_with(config, api)

    bridge.handle_event(submitted_event())
    assert bridge.drain() == 0
    (queued,) = bridge.store.pending()
    assert queued.attempts == 1
    assert queued.last_error is not None
    assert queued.is_materialised, "the bytes are fetched once and kept, so the API may go down too"

    printer = FakePrinter()
    try:
        bridge.config = make_config(
            tmp_path, printers={"kitchen": f"{printer.host}:{printer.port}"}
        )
        assert bridge.drain() == 1
        assert printer.paper(1) == [ticket_bytes]
    finally:
        printer.close()

    assert bridge.store.pending() == []
    assert len(api.fetched) == 1, "the payload is fetched once, not once per attempt"


def test_a_backlog_prints_in_the_order_the_kitchen_was_told(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    receipt = golden("receipt.bin")
    api = FakeApi(payloads={TICKET_PATH: ticket_bytes, RECEIPT_PATH: receipt})
    # One printer only, so the receipt falls back to it and both land in one place, in order.
    bridge = bridge_with(config_for(tmp_path, fake_printer), api)

    bridge.handle_event(submitted_event())
    bridge.handle_event(settled_event())
    assert bridge.drain() == 2

    assert fake_printer.paper(2) == [ticket_bytes, receipt]


def test_a_job_for_an_unconfigured_printer_is_recorded_not_lost(
    tmp_path: Path, fake_printer: FakePrinter
) -> None:
    bridge = bridge_with(config_for(tmp_path, fake_printer), FakeApi())
    bridge.store.enqueue(job_key="k", printer="bar", fetch_path="/p", description="bar ticket")

    assert bridge.drain() == 0
    (job,) = bridge.store.pending()
    assert job.last_error is not None and "not configured" in job.last_error


def test_a_job_the_server_refuses_is_dropped_with_its_reason(
    tmp_path: Path, fake_printer: FakePrinter
) -> None:
    """A 404 will still be a 404 next minute. Retrying forever would wedge the queue behind it."""

    class Refusing(FakeApi):
        def fetch_payload(self, path: str) -> bytes:
            self.fetched.append(path)
            raise ApiError(f"GET {path}: nothing to print (404)")

    bridge = bridge_with(config_for(tmp_path, fake_printer), Refusing())
    bridge.handle_event(submitted_event())

    assert bridge.drain() == 0
    assert bridge.store.pending() == []
    (job,) = bridge.store.all_jobs()
    assert job.last_error is not None and "404" in job.last_error
    assert fake_printer.paper(1, timeout=0.5) == []


# ------------------------------------------------------------------ control events


def test_resync_moves_the_cursor_and_prints_nothing(
    tmp_path: Path, fake_printer: FakePrinter
) -> None:
    """The gap was longer than the server replays. There is no retrospective paper to produce."""
    bridge = bridge_with(config_for(tmp_path, fake_printer), FakeApi())
    event = StreamEvent(event="RESYNC", event_id="900", data={"seq": 900})

    assert bridge.handle_event(event) == 0
    assert bridge.store.pending_count() == 0
    assert bridge.store.last_event_id() == "900"


def test_auth_expired_prints_nothing_and_does_not_move_the_cursor(
    tmp_path: Path, fake_printer: FakePrinter
) -> None:
    """Re-enrolling the Pi must not cost the tickets that arrived before the token lapsed."""
    bridge = bridge_with(config_for(tmp_path, fake_printer), FakeApi())
    bridge.store.set_last_event_id(412)

    event = StreamEvent(event="AUTH_EXPIRED", event_id=None, data={"detail": "Sign in again."})
    assert bridge.handle_event(event) == 0
    assert bridge.store.last_event_id() == "412"
    assert bridge.store.pending_count() == 0


def test_an_event_that_prints_nothing_still_advances_the_cursor(
    tmp_path: Path, fake_printer: FakePrinter
) -> None:
    """Otherwise every reconnect replays the whole quiet stretch between two tickets."""
    bridge = bridge_with(config_for(tmp_path, fake_printer), FakeApi())
    event = StreamEvent(
        event="ITEM_READY",
        event_id="413",
        data={"id": "e", "seq": 413, "type": "ITEM_READY", "aggregate_id": ORDER_ID},
    )

    assert bridge.handle_event(event) == 0
    assert bridge.store.last_event_id() == "413"


# ------------------------------------------------------------------ operational


def test_the_healthcheck_reports_the_queue_the_cursor_and_the_printers(
    tmp_path: Path, fake_printer: FakePrinter, caplog: pytest.LogCaptureFixture
) -> None:
    """If this line stops appearing in the journal, the bridge is wedged."""
    bridge = bridge_with(config_for(tmp_path, fake_printer), FakeApi())
    bridge.store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    bridge.store.set_last_event_id(412)

    with caplog.at_level("INFO", logger="renzy.bridge"):
        bridge.healthcheck(force=True)

    (line,) = [r.getMessage() for r in caplog.records if "healthcheck" in r.getMessage()]
    assert "queue_pending=1" in line
    assert "cursor=412" in line
    assert "kitchen=up" in line


def test_the_healthcheck_names_a_printer_that_is_down(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = make_config(tmp_path, printers={"kitchen": f"127.0.0.1:{dead_port()}"})
    bridge = bridge_with(config, FakeApi())

    with caplog.at_level("INFO", logger="renzy.bridge"):
        bridge.healthcheck(force=True)

    (line,) = [r.getMessage() for r in caplog.records if "healthcheck" in r.getMessage()]
    assert "kitchen=DOWN" in line


def test_the_healthcheck_is_rate_limited(
    tmp_path: Path, fake_printer: FakePrinter, caplog: pytest.LogCaptureFixture
) -> None:
    """Once a minute, not once an event — a busy Friday would otherwise bury the journal."""
    bridge = bridge_with(config_for(tmp_path, fake_printer), FakeApi())

    with caplog.at_level("INFO", logger="renzy.bridge"):
        bridge.healthcheck(force=True)
        bridge.healthcheck()
        bridge.healthcheck()

    assert len([r for r in caplog.records if "healthcheck" in r.getMessage()]) == 1


def test_stopping_mid_drain_leaves_the_rest_queued(
    tmp_path: Path, fake_printer: FakePrinter, ticket_bytes: bytes
) -> None:
    """SIGTERM from systemd: stop cleanly and leave the rest for the next start."""
    api = FakeApi(payloads={TICKET_PATH: ticket_bytes, RECEIPT_PATH: golden("receipt.bin")})
    bridge = bridge_with(config_for(tmp_path, fake_printer), api)
    bridge.handle_event(submitted_event())
    bridge.handle_event(settled_event())
    bridge.stop()

    assert bridge.drain() == 0
    assert bridge.store.pending_count() == 2
