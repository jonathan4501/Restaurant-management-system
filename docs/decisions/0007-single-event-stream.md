# ADR-0007 — One append-only event stream for every action, not only orders

**Status:** Accepted · 2026-09-14
**Refines:** ADR-0001

## Context

ADR-0001 makes `order_events` the source of truth and gives the owner "every action by every person"
by construction. But the event vocabulary in `03-data-model.md` already contains actions that are not
about an order: `SESSION_OPENED`, `SHIFT_OPENED`, `SHIFT_CLOSED`, `DRAWER_COUNTED`, `ITEM_86ED`,
`PIN_FAILED`. The table as first drafted had `order_id UUID NOT NULL`, so those events had nowhere to go.

Three ways to resolve it were considered:

| | Shape | Verdict |
|---|---|---|
| One table per aggregate | `order_events`, `shift_events`, `menu_events`, `device_events` | Rejected. The owner's "every action, in order" screen and the SSE `Last-Event-ID` replay both need **one** ordered sequence. Four tables means four sequences to merge. |
| Order events plus a separate `audit_log` | Non-order actions go to a mutable side table | Rejected. This is exactly the two-tables-that-can-disagree failure ADR-0001 exists to prevent. |
| **One stream, typed by aggregate** | Keep `order_events`, add `aggregate_type` + `aggregate_id`, make `order_id` nullable | **Accepted.** |

## Decision

`order_events` remains the single append-only source of truth and keeps its name (it is named in
`CLAUDE.md` and every doc). It gains:

- `aggregate_type TEXT NOT NULL` ∈ `ORDER`, `SESSION`, `SHIFT`, `MENU_ITEM`, `DEVICE`, `STAFF`
- `aggregate_id UUID NOT NULL` — the id of that aggregate
- `order_id UUID NULL` — still present and indexed, set for every `ORDER` event and for `SESSION` events
  that concern one order, so "what happened to order 1046" stays a single indexed query
- `reason_code TEXT NULL` — the mandatory reason on authorised actions, promoted out of the payload so it
  can be filtered and reported without JSON queries

`seq` is **per restaurant and gapless in commit order**. It is assigned inside the command transaction
under a per-restaurant advisory lock (`pg_advisory_xact_lock`), not by a global `BIGSERIAL`. A global
serial can commit out of order (seq 10 commits before seq 9), and a client that has seen 10 would never
receive 9 on `Last-Event-ID` replay. The lock removes that race. At one restaurant its cost is nil; at
many restaurants the lock is per tenant so restaurants never wait on each other.

`UNIQUE (restaurant_id, seq)`.

## Consequences

- One `GET /stream` and one `Last-Event-ID` cover the kitchen, cashier and owner. One replay path.
- The owner's event log is `SELECT … ORDER BY seq`, filterable by `aggregate_type`, `actor_id`,
  `event_type`, `reason_code`. No joins across audit tables.
- Every command in the system, not only order commands, goes through the same runner
  (`docs/08-backend-architecture.md`). There is no second write path to forget.
- Projection tables exist per aggregate (`orders`, `order_items`, `table_sessions`, `shifts`,
  `menu_items.is_available`). Each is rebuildable from the stream filtered by its `aggregate_type`.

## Revisit when

Event volume makes a single per-restaurant sequence a write bottleneck — which, at one event per human
action, is not a restaurant-scale problem.
