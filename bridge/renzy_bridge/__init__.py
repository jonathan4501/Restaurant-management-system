"""
RENZY print bridge — the Raspberry Pi daemon that turns stream events into paper.

Browsers cannot open a TCP socket to an ESC/POS printer, so something on the restaurant's LAN has
to. This package is that something: it consumes the server's event stream, queues print jobs on
local disk, and pushes ESC/POS bytes at printers on TCP:9100.

It deliberately holds no business logic. The ESC/POS bytes are rendered server-side by
`apps.printing`, where they are covered by golden-file tests; the bridge's only jobs are to be
durable, to reconnect, and never to print the same thing twice.
"""

__version__ = "0.1.0"
