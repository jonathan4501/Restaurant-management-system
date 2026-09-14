# WS06 — Reporting

**Goal:** the four owner panels from `01-product-spec.md §8`, in that order, and the daily summary
pushed to the owner at close.

**Depends on:** WS03, WS05. **Blocks:** WS10.

## Owns

`backend/apps/reporting/`, `config/celery.py` beat schedule entries for this app.

## Endpoints

`GET /reports/variance` · `GET /reports/today` · `GET /reports/patterns` · `GET /events/log`.

## Build

1. `daily_sales` rollup task `rollup_daily_sales(restaurant_id, business_date)`: idempotent upsert;
   scheduled by beat at `day_cutover_hour + 10 min` per restaurant; also runnable via
   `manage.py rollup_daily_sales --date`. Columns as in `03-data-model.md`.
2. Variance endpoint: voids after acknowledgement (value, reason, actor, authoriser, order number),
   discounts and comps grouped by staff member, reopened sessions, cash variance per shift and cashier,
   order-number gaps per business date (expected consecutive numbers vs present). All from projections and
   `order_events` **filtered by type and indexed columns** — no folding, no JSON scans across the whole log.
3. Today: `money_taken_pesewas` so far, covers (Σ `party_size` of settled sessions), average bill,
   open bills now. Computed live from projections (today is not rolled up yet).
4. Patterns: money taken by hour (business-date aware), payment method mix, top 20 items by value
   (from `order_items` snapshots), average `acknowledged_at → ready_at` per station.
5. Event log endpoint: cursor pagination by `seq` desc, filters `actor_id`, `type`, `aggregate_type`,
   `from/to`; `flagged` derived from the flagged set in `03-data-model.md`; joins actor and authoriser names.
6. Daily summary: Celery task after rollup renders a short text (money taken, covers, voids, variance,
   top 3 items) and sends by email (SMTP env) — WhatsApp via Twilio is a stub behind a `SummarySender`
   interface; do not add the dependency until the owner confirms the channel.
7. OpenAPI descriptions: every gross money field described as "Money taken (gross cash through the till)".

## Tests required

- Rollup twice for the same date → one row, same numbers.
- Variance fixtures: a void before ack does **not** appear; a void after ack does, with both names.
- Order-number gap detection: numbers 1,2,4 → gap `[3]`.
- Business-date boundaries: an order at 02:30 belongs to the previous date.
- Event log: `flagged` true for `DISCOUNT_APPLIED`, false for `ORDER_SERVED`; cursor pages do not overlap.

## Exit criteria

Against the WS05 `service_script.py` fixture, every number on the four endpoints can be reconciled by
hand from the fixture, and the daily summary email renders in the dev mailbox.
