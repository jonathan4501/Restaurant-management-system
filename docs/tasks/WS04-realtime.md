# WS04 — Realtime

**Goal:** a kitchen tablet that loses WiFi for 90 seconds reconnects and receives exactly the events it
missed, in order, and nothing it should not see.

**Depends on:** WS03 (real events to stream). **Blocks:** WS08, WS09, WS12.

## Owns

`backend/apps/realtime/`.

## Build

1. Harden the WS00 stream: role filtering (`filters.py::visible_to`), heartbeat 15 s, graceful close on
   client disconnect (`asyncio.CancelledError`), a hard cap of one replay batch of 1 000 events before going
   live (older gaps mean a cold reload — return `event: RESYNC` and let the client refetch).
2. `GET /events?since&limit` polling fallback with the same filtering.
3. Connection accounting: `stream_connections{restaurant, role}` gauge exposed at `/metrics` (plain text;
   Prometheus format is fine, nothing scrapes it yet).
4. Device `last_seen_at` updated on stream connect (throttled to once per minute).
5. Revoked device or expired staff token → stream closes with `event: AUTH_EXPIRED` then EOF; client
   goes to the login screen rather than retrying forever.
6. Document the client contract in `frontend/lib/realtime/README.md`: EventSource, `Last-Event-ID`,
   dedupe by `seq`, fallback to polling after two failures, retry stream every 30 s, `RESYNC` handling.

## Tests required

- Integration with real Redis: connect, publish through `run_command`, receive; disconnect, publish two,
  reconnect with `Last-Event-ID`, receive exactly those two in order.
- KITCHEN principal does not receive `PAYMENT_RECORDED`; CASHIER does.
- Two restaurants: neither sees the other's events (tenant isolation on the channel name and the replay query).
- Polling endpoint returns the same envelopes as the stream for the same `since`.
- Revoked device mid-stream → `AUTH_EXPIRED` and close.

## Exit criteria

Step 4 of the `curl` walk-through works with a real service of events from WS03; the kitchen filter is
demonstrated in a test.
