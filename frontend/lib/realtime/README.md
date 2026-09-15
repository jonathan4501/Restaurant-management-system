# Realtime client contract

How a staff screen (KDS, cashier, waiter, owner) stays current. Server side: `backend/apps/realtime/`,
format in `docs/09-api-contract.md` §4. Guests have no stream — they poll their own order.

## Cold start, then updates

1. **Open the stream first** (no `Last-Event-ID` on a cold start), then fetch the screen's state with
   normal GETs (`/tables`, `/orders/{id}`, …), then invalidate for anything that arrived meanwhile. Opening
   the stream after the GETs leaves a window where an event is in neither. From then on remember the
   highest `seq` applied.
2. Connecting: `EventSource` cannot send headers, so use `fetch` with a streaming body reader (or an
   EventSource polyfill that accepts headers):

   ```
   GET /api/v1/stream
   X-Device-Token: <device token>
   Authorization: Bearer <staff token>
   Last-Event-ID: <last applied seq>      # omit on first connect
   ```

3. For each message: `id:` is the `seq`, `event:` is the type, `data:` is the envelope JSON. Lines starting
   with `:` are keepalives (every 15 s) — ignore them, but use them to reset a "stream is alive" timer
   (treat 40 s of silence as a failure).

## Rules

- **Dedupe by `seq`.** Drop any envelope whose `seq` ≤ the last one applied. Replay and live can overlap by
  design; the server also skips duplicates, but the client must not depend on that.
- **Apply in order.** `seq` is per restaurant and gapless; the stream only omits events your role may not
  see, so gaps in what you receive are normal.
- **Reconnect with `Last-Event-ID`.** The server replays `seq > Last-Event-ID` first, then goes live.
- **Invalidate by aggregate.** Map `aggregate_type` + `aggregate_id` / `order_id` to TanStack Query keys and
  patch or invalidate. Payloads carry enough to render without a follow-up GET.

## Control events

| `event:` | Meaning | Client action |
|---|---|---|
| `RESYNC` | You missed more than 1 000 events. `id:`/`data.seq` is the current head. | Store `seq` as last applied, refetch the whole screen (invalidate all queries), keep the stream open — it continues live. |
| `AUTH_EXPIRED` | Device revoked, staff token expired or logged out, or staff retired. The server closes the stream right after. | Clear the staff session, go to `/login`. **Do not retry the stream.** A revoked device also clears its device token. |

A `401` or `403` on connect means the same as `AUTH_EXPIRED`.

## Failure and fallback

```
stream fails (network error, non-200, or 40 s silence)
  → retry once immediately with Last-Event-ID
  → second consecutive failure: switch to polling
      GET /api/v1/events?since=<last_seq>&limit=200   every 3 s
      apply `events`, then set since = response.last_seq
      if has_more: call again immediately
  → while polling, try the stream again every 30 s; on success stop polling
```

`last_seq` from `/events` is the highest `seq` the server **scanned**, including events hidden from your
role. Always send it back as `since` — using the last visible event's `seq` would re-fetch the same hidden
events forever.

Offline writes are a separate concern: the IndexedDB outbox (WS11) replays commands; the stream only
delivers what the server has committed.
