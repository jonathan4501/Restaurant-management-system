"""
Pushing ESC/POS bytes at a printer over TCP:9100.

Every network receipt printer speaks this: open a socket, write the bytes, close. There is no
acknowledgement and no status in the stream, so "the socket accepted it" is as much certainty as
the protocol offers. That is why the queue only marks a job printed after `send()` returns, and why
a printer that is switched off raises rather than silently succeeding.
"""

from __future__ import annotations

import socket

from .config import Printer


class PrinterUnreachable(RuntimeError):
    """The printer did not accept a connection: switched off, unplugged, or wrong address."""


def send(target: Printer, payload: bytes, *, timeout: float = 5.0) -> None:
    try:
        with socket.create_connection((target.host, target.port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            connection.sendall(payload)
    except OSError as err:
        raise PrinterUnreachable(f"{target}: {err}") from err


def probe(target: Printer, *, timeout: float = 2.0) -> bool:
    """Is the printer answering? Used by the healthcheck line, never to gate a print."""
    try:
        with socket.create_connection((target.host, target.port), timeout=timeout):
            return True
    except OSError:
        return False
