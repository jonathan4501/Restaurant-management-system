# WS03 — Orders core

**Goal:** the order lifecycle from `ORDER_OPENED` to `ORDER_CLOSED`/`ORDER_VOIDED`, every transition
enforced server-side, every line snapshotted, every total an integer, every projection rebuildable.

**Depends on:** WS00, WS01 (principals in tests), WS02 (`snapshot_line`). **Blocks:** WS04, WS05, WS07, WS08.

## Owns

`backend/apps/orders/` (fill in what WS00 stubbed), `backend/apps/floor/`.

## Endpoints

Floor: `GET /tables` · `POST /sessions` · `GET /sessions/{id}` · `GET /sessions/{id}/bill` · `POST /sessions/{id}/close`.
Orders: everything under `/orders` in `08-api-contract.md §3` except `/fire` (return 501).
KDS read: `GET /kds/tickets`.
Guest router: `POST /guest/orders`, `/items`, `/remove`, `/modify`, `/submit`, `GET /guest/orders/{id}`.

## Events

`SESSION_OPENED` `SESSION_CLOSED` `ORDER_OPENED` `ITEM_ADDED` `ITEM_REMOVED` `ITEM_MODIFIED`
`ORDER_SUBMITTED` `KITCHEN_ACKNOWLEDGED` `ITEM_STARTED` `ITEM_READY` `ORDER_READY` `ORDER_SERVED`
`DISCOUNT_APPLIED` `COMP_APPLIED` `PRICE_OVERRIDDEN` `ORDER_VOIDED`. (`ORDER_CLOSED`, `ORDER_REOPENED`
are emitted by WS05's settlement/reopen handlers, but their **projectors** live here.)

## Build

1. `commands/` — one module per command, each a function `handle(ctx, order_id, data) -> CommandOutcome`
   that: locks the order (`select_for_update`), calls `state_machine.transition`, validates, builds events.
   Item commands go through `menu.snapshot.snapshot_line`. Never read a price anywhere else.
2. `totals.py` — `line_total`, `order_total`, `apply_percent_discount` (half-up to the pesewa, `Decimal`
   only inside). Hypothesis tests.
3. `submit`: assigns `business_date` (`core.business_date`) and `order_number` from `OrderCounter`
   (`select_for_update`, create if missing). Rejects empty orders (422). Payload includes everything the
   KDS and printer need: order number, table number, lines with snapshots and modifiers, notes, course,
   station per line, totals.
4. `projector.py` — handlers for every event above, updating `orders`, `order_items`, `table_sessions`
   (`bill_total_pesewas`). Deterministic; uses `event.created_at` for timestamps.
5. `rebuild_projections` / `verify_projections` fully working: rebuild in a transaction; verify diffs
   `orders`, `order_items`, `table_sessions` row by row and exits non-zero on drift.
6. Void: from `SUBMITTED` no authorisation; from `PREPARING`/`READY`/`SERVED` requires purpose
   `VOID_AFTER_ACK`. Payload carries `status_at_void`, `total_pesewas`, `reason_code`, `note`. Voided orders
   drop out of the session bill total.
7. Discounts/comps/price override with authorisation; `discount_pesewas` ≤ `subtotal`; `COMP` = discount
   equal to subtotal with `kind: COMP`.
8. KDS read: orders in `SUBMITTED/PREPARING/READY` for the restaurant, items filtered by `?station=`,
   with `submitted_at`, `acknowledged_at`, `ready_at`, so timers are computed client-side from server times.
9. Guest router: reuse the same handlers with `ctx.actor_role=GUEST`, `actor_id=None`, `origin` from token
   mode; every lookup filtered by `principal.session_id`; 404 on anything else.
10. `GET /tables`: each table with its open session summary and the cashier state chip
    (`sent` / `cooking` / `food_ready` / `ready_to_pay` / `part_paid`) computed from the session's orders and payments.

## Tests required

- `test_state_machine.py` exhaustive (WS00 wrote it; extend for any command you add).
- One integration test per command: event appended with correct actor/device/authoriser, projection
  updated, envelope published (use the `published` fixture that captures Redis publishes).
- Snapshot test: change the menu price after submit; `GET /sessions/{id}/bill` is unchanged.
- Order numbers: two submits on the same business date are consecutive; a draft that is never submitted
  leaves no gap; 03:59 and 04:01 Accra time land on different business dates.
- Concurrency: two parallel submits for different orders in one restaurant get distinct, consecutive `seq`
  (thread test against real Postgres).
- `verify_projections` reports zero drift after a scripted service of 30 orders including voids and discounts.
- Guest cannot touch another session: 404. Guest cannot ack: 403.

## Exit criteria

The `curl` walk-through in `08-api-contract.md §6` step 3 works, including the idempotent replay, and
`verify_projections` is clean afterwards.
