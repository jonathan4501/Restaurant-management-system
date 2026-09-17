"""
The durable queue and the stream cursor.

Two properties are load-bearing and both are asserted here: enqueueing the same key twice creates
one job, and a payload comes back out of SQLite byte-identical to what went in. The second matters
because ESC/POS is binary with embedded NULs — a store that round-tripped it through `str` would
produce plausible-looking paper with the wrong cut and the wrong code page.
"""

from __future__ import annotations

from pathlib import Path

from conftest import golden

from renzy_bridge.store import Store


def test_a_fresh_store_has_no_cursor_and_no_work(store: Store) -> None:
    assert store.last_event_id() is None
    assert store.pending() == []
    assert store.pending_count() == 0


def test_enqueue_returns_true_once_and_false_ever_after(store: Store) -> None:
    """False is not an error: on a reconnect it is the answer that stops the second ticket."""
    assert store.enqueue(job_key="k", printer="kitchen", fetch_path="/p", description="d") is True
    assert store.enqueue(job_key="k", printer="kitchen", fetch_path="/p", description="d") is False
    assert store.pending_count() == 1


def test_a_replay_cannot_overwrite_a_job_already_in_flight(store: Store) -> None:
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/first", description="first")
    store.enqueue(job_key="k", printer="front", fetch_path="/second", description="second")
    (job,) = store.pending()
    assert (job.printer, job.fetch_path) == ("kitchen", "/first")


def test_a_printed_job_is_not_re_enqueued_by_a_later_replay(store: Store) -> None:
    """The strongest statement of the no-double-print rule: printed keys stay known."""
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.mark_printed("k")
    assert store.enqueue(job_key="k", printer="kitchen", fetch_path="/p") is False
    assert store.pending() == []
    assert store.is_printed("k")


def test_pending_comes_back_oldest_first(store: Store) -> None:
    """Tickets must reach the pass in the order the kitchen was told about them."""
    for key in ("a", "b", "c"):
        store.enqueue(job_key=key, printer="kitchen", fetch_path=f"/{key}")
    assert [job.job_key for job in store.pending()] == ["a", "b", "c"]


def test_escpos_bytes_survive_the_round_trip_exactly(store: Store) -> None:
    payload = golden("kitchen_ticket.bin")
    assert b"\x00" in payload or b"\x1b" in payload, "golden should be real binary ESC/POS"
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.store_payload("k", payload)
    (job,) = store.pending()
    assert job.payload == payload
    assert job.is_materialised


def test_a_payload_is_not_attached_to_an_already_printed_job(store: Store) -> None:
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.mark_printed("k")
    store.store_payload("k", b"late")
    assert [job.payload for job in store.all_jobs()] == [None]


def test_a_failure_is_counted_and_kept_for_the_operator(store: Store) -> None:
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.record_failure("k", "printer off")
    store.record_failure("k", "printer still off")
    (job,) = store.pending()
    assert job.attempts == 2
    assert job.last_error == "printer still off"


def test_printing_clears_a_stale_failure(store: Store) -> None:
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.record_failure("k", "printer off")
    store.mark_printed("k")
    assert [job.last_error for job in store.all_jobs()] == [None]


def test_abandoning_a_job_keeps_the_reason_it_never_printed(store: Store) -> None:
    """`mark_printed` clears last_error, so a dropped job needs its own statement or the reason
    for the missing ticket disappears from the only place anyone would look."""
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.abandon("k", "GET /p: nothing to print (404)")
    (job,) = store.all_jobs()
    assert store.pending() == []
    assert job.last_error == "GET /p: nothing to print (404)"


def test_a_long_error_is_truncated_rather_than_filling_the_sd_card(store: Store) -> None:
    store.enqueue(job_key="k", printer="kitchen", fetch_path="/p")
    store.record_failure("k", "x" * 5000)
    (job,) = store.pending()
    assert job.last_error is not None
    assert len(job.last_error) == 500


def test_the_cursor_survives_reopening_the_file(tmp_path: Path) -> None:
    """The Pi loses power; the next start must resume the stream, not restart it."""
    path = tmp_path / "state.sqlite3"
    with Store(path) as first:
        first.set_last_event_id(412)
    with Store(path) as second:
        assert second.last_event_id() == "412"


def test_the_cursor_is_stored_as_a_string_whatever_it_arrives_as(store: Store) -> None:
    store.set_last_event_id(1)
    store.set_last_event_id("2")
    assert store.last_event_id() == "2"


def test_the_queue_survives_reopening_the_file(tmp_path: Path) -> None:
    path = tmp_path / "state.sqlite3"
    payload = golden("receipt.bin")
    with Store(path) as first:
        first.enqueue(job_key="k", printer="front", fetch_path="/p", description="receipt")
        first.store_payload("k", payload)
    with Store(path) as second:
        (job,) = second.pending()
        assert job.payload == payload


def test_a_missing_parent_directory_is_created(tmp_path: Path) -> None:
    """First boot on a fresh Pi: /var/lib/renzy-bridge does not exist yet."""
    with Store(tmp_path / "nested" / "deeper" / "state.sqlite3") as opened:
        assert opened.pending_count() == 0


def test_purge_removes_old_paper_and_leaves_pending_work(store: Store) -> None:
    store.enqueue(job_key="old", printer="kitchen", fetch_path="/o")
    store.enqueue(job_key="new", printer="kitchen", fetch_path="/n")
    store.mark_printed("old")
    assert store.purge_printed(keep_days=-1) == 1
    assert [job.job_key for job in store.all_jobs()] == ["new"]
