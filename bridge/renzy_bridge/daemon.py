"""
The bridge daemon: consume the stream, queue paper, push it at printers.

The loop, and why it is in this order:

    1. drain the queue           — anything left from the last run prints before new work
    2. open the stream with Last-Event-ID
    3. for each event: queue jobs, *then* move the cursor, then drain
    4. on any disconnect: back off and reconnect from the stored cursor

Step 3's order is the whole correctness argument. Jobs reach disk before the cursor advances, so a
crash re-delivers the event rather than skipping it; and `Store.enqueue` ignores a `job_key` it has
already seen, so that re-delivery prints nothing twice. Restart the Pi mid-service and the worst
case is a ticket that prints once, late — never twice, never not at all.
"""

from __future__ import annotations

import logging
import random
import signal
import time
from types import FrameType

from . import printer as printer_io
from .api import ApiClient, ApiError, ApiUnavailable, StreamEvent
from .config import Config
from .jobs import PrintJob, jobs_for
from .store import QueuedJob, Store

log = logging.getLogger("renzy.bridge")


class Bridge:
    def __init__(self, config: Config, store: Store, api: ApiClient) -> None:
        self.config = config
        self.store = store
        self.api = api
        self._stop = False
        self._last_healthcheck = 0.0

    # ---------------------------------------------------------------- lifecycle

    def stop(self, *_: object) -> None:
        """SIGTERM from systemd. Finish the current job, then exit cleanly."""
        log.info("stopping: signal received")
        self._stop = True

    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, self._handle_signal)

    def _handle_signal(self, signum: int, frame: FrameType | None) -> None:
        del signum, frame
        self.stop()

    # ---------------------------------------------------------------- events

    def handle_event(self, event: StreamEvent) -> int:
        """
        Queue the paper for one event and advance the cursor. Returns how many jobs were new.

        A replayed event returns 0: the jobs are already in the store, printed or pending.
        """
        if event.event == "AUTH_EXPIRED":
            log.error("stream says the device is no longer authorised — re-enrol the Pi")
            return 0

        if event.event == "RESYNC":
            # The gap was too long for the server to replay. Nothing to print retrospectively; jump
            # to the head so live events keep flowing, and say so loudly because paper was missed.
            seq = event.data.get("seq")
            if seq is not None:
                self.store.set_last_event_id(seq)
            log.warning(
                "stream resynced at seq %s: the gap was longer than the server replays, so any "
                "ticket submitted during it was not printed",
                seq,
            )
            return 0

        envelope = event.data
        new = 0
        for job in jobs_for(envelope, self.config):
            if self.store.enqueue(
                job_key=job.job_key,
                printer=job.printer,
                fetch_path=job.fetch_path,
                description=job.description,
            ):
                new += 1
                log.info("queued %s on %s", job.description, job.printer)
            else:
                log.debug("already seen, not printing again: %s", job.job_key)

        # Only now: every job for this event is on disk.
        if event.event_id is not None:
            self.store.set_last_event_id(event.event_id)
        return new

    # ---------------------------------------------------------------- printing

    def drain(self) -> int:
        """
        Try every pending job once. Returns how many printed.

        Failures are left in the queue with the error recorded; the next tick tries again. A
        printer that is off therefore accumulates tickets and prints the backlog when it is
        switched on, which is the behaviour the restaurant actually needs.
        """
        printed = 0
        for job in self.store.pending():
            if self._stop:
                break
            if self._print_one(job):
                printed += 1
        return printed

    def _print_one(self, job: QueuedJob) -> bool:
        target = self.config.printer(job.printer)
        if target is None:
            log.error("job %s wants printer '%s', which is not configured", job.job_key, job.printer)
            self.store.record_failure(job.job_key, f"printer '{job.printer}' not configured")
            return False

        payload = job.payload
        if payload is None:
            # Fetch the bytes once and keep them: after this the job can print with the API down.
            try:
                payload = self.api.fetch_payload(job.fetch_path)
            except ApiError as err:
                # A deterministic refusal (404 / not authorised). Retrying forever will not fix it.
                log.error("dropping %s: %s", job.description or job.job_key, err)
                self.store.abandon(job.job_key, str(err))
                return False
            except ApiUnavailable as err:
                log.warning("cannot fetch %s yet: %s", job.description or job.job_key, err)
                self.store.record_failure(job.job_key, str(err))
                return False
            self.store.store_payload(job.job_key, payload)

        try:
            printer_io.send(target, payload, timeout=self.config.printer_timeout_seconds)
        except printer_io.PrinterUnreachable as err:
            log.warning(
                "%s still queued (attempt %s): %s", job.description or job.job_key, job.attempts + 1, err
            )
            self.store.record_failure(job.job_key, str(err))
            return False

        self.store.mark_printed(job.job_key)
        log.info("printed %s on %s", job.description or job.job_key, target)
        return True

    # ---------------------------------------------------------------- health

    def healthcheck(self, force: bool = False) -> None:
        """One line a minute. If this stops appearing in the journal, the bridge is wedged."""
        now = time.monotonic()
        if not force and now - self._last_healthcheck < self.config.healthcheck_seconds:
            return
        self._last_healthcheck = now
        reachable = {
            name: printer_io.probe(target) for name, target in self.config.printers.items()
        }
        log.info(
            "healthcheck queue_pending=%s cursor=%s printers=%s",
            self.store.pending_count(),
            self.store.last_event_id(),
            ",".join(f"{n}={'up' if ok else 'DOWN'}" for n, ok in sorted(reachable.items())),
        )

    # ---------------------------------------------------------------- main loop

    def run(self) -> None:
        log.info("renzy print bridge starting: %s", self.config.redacted())
        # Whatever the last run did not finish comes out of the printer before anything new.
        self.drain()
        self.healthcheck(force=True)

        backoff = self.config.reconnect_min_seconds
        while not self._stop:
            since = self.store.last_event_id()
            try:
                log.info("connecting to stream (Last-Event-ID=%s)", since)
                for event in self.api.stream(since):
                    if self._stop:
                        break
                    backoff = self.config.reconnect_min_seconds
                    self.handle_event(event)
                    self.drain()
                    self.healthcheck()
                if not self._stop:
                    log.info("stream closed by the server; reconnecting")
            except ApiError as err:
                log.error("%s", err)
            except ApiUnavailable as err:
                log.warning("stream unavailable: %s", err)
            except Exception:  # noqa: BLE001 - a daemon must not die on an unexpected error
                log.exception("unexpected error in the stream loop")

            if self._stop:
                break

            # Keep printing and reporting while the network is down.
            self.drain()
            self.healthcheck()
            delay = min(backoff, self.config.reconnect_max_seconds)
            # Jitter so a restaurant-wide power blip does not have every device reconnect in step.
            time.sleep(delay * (0.5 + random.random() * 0.5))
            backoff = min(backoff * 2, self.config.reconnect_max_seconds)

        log.info("renzy print bridge stopped (%s job(s) pending)", self.store.pending_count())


def build(config: Config) -> Bridge:
    return Bridge(config, Store(config.state_path), ApiClient(config))


__all__ = ["Bridge", "PrintJob", "build"]
