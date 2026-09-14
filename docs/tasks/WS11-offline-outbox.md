# WS11 — Offline outbox and service worker

**Goal:** a 30-minute internet cut passes without anyone in the restaurant noticing, and nobody is ever
told the kitchen has an order it does not have.

**Depends on:** WS07. **Blocks:** nothing (but Phase 2 exit depends on it).

## Owns

`frontend/lib/outbox/`, `frontend/sw/`, the connectivity badge in the shell.

## Build

1. **Service worker** with Serwist: precache the app shell; runtime cache `GET /menu` (stale-while-
   revalidate, respects ETag) and `/tables`; network-only for commands and the stream. Versioned; prompt
   "Update available" rather than reloading mid-service.
2. **Outbox** (`idb`): store `outbox` keyed by `id` (uuid7) with `seq` (monotonic per device), `method`,
   `path`, `body`, `idempotency_key`, `client_time`, `status` (`queued` / `sending` / `failed`), `attempts`,
   `last_error`. Every command from `lib/api/client.ts` goes **through the outbox**, online or not: write,
   then attempt, then mark. That is what makes replay safe.
3. **Drain**: FIFO, one in flight, exponential backoff 1 s → 30 s, resumes on `online` event, on stream
   reconnect, and on app focus. 4xx other than 409/429 → `failed` and surfaced to the user (a void the
   server rejected must be seen, not silently dropped). 5xx and network → retry.
4. **Honest UI**: every optimistic entity carries `pending: true` until its command's 2xx arrives; the
   draft panel shows "Sending… (queued: N)" and the KDS-bound order is **not** shown as "sent to kitchen"
   until confirmed. The badge shows offline/pending counts. Never lie about this.
5. **Reconnect sequence**: drain outbox → reconnect stream with `Last-Event-ID` → invalidate queries.
6. **Server-authoritative state**: item availability (86) and payment status render as pending while offline
   and never as final.
7. **Guest/qr mode** does not use the outbox (a guest's phone with no network simply cannot order; say so).

## Tests required

- Vitest with fake-indexeddb: enqueue 5, drain in order, failure mid-way retries without reordering,
  duplicate submission with the same key is not re-enqueued.
- Playwright: go offline (context.setOffline), send two orders, go online, both arrive once (mock asserts
  keys) and the badge clears.

## Exit criteria

The Phase 2 exit test from `04-build-plan.md`: pull the router's WAN for 30 minutes during a scripted
service; every order sent during the gap reaches the kitchen exactly once afterwards, and the timeline
in the event log shows `client_created_at` inside the gap and `created_at` after it.
