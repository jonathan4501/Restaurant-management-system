"""
Which events produce paper, and on which printer.

A pure function: envelope in, list of jobs out. No sockets, no database, no clock — so the
reconnect and de-duplication behaviour is testable without a printer or a server.

`job_key` is derived from the **event id**, which the server assigns once and never changes. That
is what makes a replayed event a no-op: the same event yields the same key, and the store's primary
key rejects the second insert. Two different events that happen to print the same bill (a
settlement and a later explicit reprint) have different ids and are meant to produce two pieces of
paper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import FRONT, KITCHEN, Config

# Events that produce paper. Anything else on the stream is ignored.
ORDER_SUBMITTED = "ORDER_SUBMITTED"
SESSION_SETTLED = "SESSION_SETTLED"
RECEIPT_REQUESTED = "RECEIPT_REQUESTED"

PRINTABLE = frozenset({ORDER_SUBMITTED, SESSION_SETTLED, RECEIPT_REQUESTED})


@dataclass(frozen=True)
class PrintJob:
    job_key: str
    printer: str
    fetch_path: str
    description: str


def _stations(envelope: dict[str, Any]) -> list[str]:
    """
    Prep stations with work on this order, read straight off the envelope.

    The ORDER_SUBMITTED payload carries every line with its `prep_station`, so the bridge can split
    a ticket per station without asking the server anything.
    """
    seen: list[str] = []
    for line in (envelope.get("payload") or {}).get("lines") or []:
        station = line.get("prep_station")
        if station and station not in seen:
            seen.append(station)
    return sorted(seen)


def jobs_for(envelope: dict[str, Any], config: Config) -> list[PrintJob]:
    event_type = envelope.get("type")
    if event_type not in PRINTABLE:
        return []

    event_id = envelope.get("id")
    if not event_id:
        return []

    if event_type == ORDER_SUBMITTED:
        return _ticket_jobs(envelope, config, str(event_id))
    return _receipt_jobs(envelope, config, str(event_id), reprint=event_type == RECEIPT_REQUESTED)


def _ticket_jobs(envelope: dict[str, Any], config: Config, event_id: str) -> list[PrintJob]:
    """
    One ticket, or one per station.

    With no `[stations]` in the config — the normal RENZY setup, a single printer in the kitchen —
    the whole ticket prints once, unsplit. Configure `[stations]` and each station on the order gets
    its own ticket carrying only its own lines, on the printer that serves it.
    """
    order_id = envelope.get("order_id") or envelope.get("aggregate_id")
    if not order_id:
        return []
    payload = envelope.get("payload") or {}
    number = payload.get("order_number", "?")
    table = payload.get("table_number", "?")

    if config.station_printers:
        targets = [(config.printer_for_station(s), s) for s in _stations(envelope)]
    else:
        targets = [(KITCHEN, None)]

    jobs: list[PrintJob] = []
    for printer_name, station in targets:
        # A misconfigured station must still produce paper somewhere rather than vanish.
        resolved = printer_name if printer_name in config.printers else _fallback(config)
        query = f"?station={station}" if station else ""
        suffix = f" [{station}]" if station else ""
        jobs.append(
            PrintJob(
                job_key=f"{event_id}:{resolved}:{station or 'all'}",
                printer=resolved,
                fetch_path=f"/api/v1/print/tickets/{order_id}{query}",
                description=f"ticket #{number} table {table}{suffix}",
            )
        )
    return jobs


def _fallback(config: Config) -> str:
    for name in (KITCHEN, FRONT):
        if name in config.printers:
            return name
    return next(iter(config.printers))


def _receipt_jobs(
    envelope: dict[str, Any], config: Config, event_id: str, *, reprint: bool
) -> list[PrintJob]:
    session_id = envelope.get("aggregate_id")
    if not session_id:
        return []
    printer_name = FRONT if FRONT in config.printers else _fallback(config)
    payload = envelope.get("payload") or {}
    table = payload.get("table_number", "?")
    # The server decides whether this counts as a reprint; it has the event log. We pass its answer
    # through so the paper says so.
    is_reprint = bool(payload.get("reprint", reprint))
    query = "?reprint=1" if is_reprint else ""
    label = "receipt reprint" if is_reprint else "receipt"
    return [
        PrintJob(
            job_key=f"{event_id}:{printer_name}",
            printer=printer_name,
            fetch_path=f"/api/v1/print/receipts/{session_id}{query}",
            description=f"{label} table {table}",
        )
    ]
