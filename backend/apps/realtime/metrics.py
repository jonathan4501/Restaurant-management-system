"""
Connection accounting for the SSE stream: a `stream_connections{restaurant, role}` gauge.

Per process. Uvicorn runs one process per worker, so a scrape sees the worker it lands on; that is
enough to spot "the kitchen has not been connected for ten minutes". Nothing scrapes it yet (WS04).
"""

from __future__ import annotations

import threading
import uuid
from collections import Counter

_lock = threading.Lock()
_connections: Counter[tuple[str, str]] = Counter()


def connected(restaurant_id: uuid.UUID, role: str) -> None:
    with _lock:
        _connections[(str(restaurant_id), role)] += 1


def disconnected(restaurant_id: uuid.UUID, role: str) -> None:
    key = (str(restaurant_id), role)
    with _lock:
        _connections[key] -= 1
        if _connections[key] <= 0:
            del _connections[key]


def connection_count(restaurant_id: uuid.UUID, role: str) -> int:
    with _lock:
        return _connections.get((str(restaurant_id), role), 0)


def render() -> str:
    """Prometheus text exposition format."""
    lines = [
        "# HELP stream_connections Open SSE stream connections.",
        "# TYPE stream_connections gauge",
    ]
    with _lock:
        rows = sorted(_connections.items())
    for (restaurant, role), count in rows:
        lines.append(f'stream_connections{{restaurant="{restaurant}",role="{role}"}} {count}')
    return "\n".join(lines) + "\n"
