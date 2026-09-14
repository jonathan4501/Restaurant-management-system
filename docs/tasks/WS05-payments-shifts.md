# WS05 — Payments, shifts and the drawer

**Goal:** the money question. Every cedi through the till is attached to a shift; every bill settles by
the rules in ADR-0008; the cashier's declared cash is compared with what the system expected.

**Depends on:** WS03. **Blocks:** WS06, WS09.

## Owns

`backend/apps/payments/`.

## Endpoints

`GET /shifts/current` · `POST /shifts` · `POST /shifts/{id}/movements` · `POST /shifts/{id}/close` ·
`GET /shifts/{id}/z-report` · `GET /bills/open` · `POST /sessions/{id}/payments` · `POST /payments/{id}/void` ·
`POST /sessions/{id}/reopen`.

## Events

`SHIFT_OPENED` `DRAWER_MOVEMENT` `DRAWER_COUNTED` `SHIFT_CLOSED` `PAYMENT_RECORDED` `PAYMENT_VOIDED`
`SESSION_SETTLED` `SESSION_REOPENED` and, emitted by settlement/reopen for each order, `ORDER_CLOSED`
`ORDER_REOPENED` (projectors in WS03).

## Build

1. Shift open/close as commands; one open shift per cashier (partial unique index exists). Close computes
   `expected_cash_pesewas` from projections: `float + Σ CASH payments − Σ PAID_OUT + Σ PAID_IN`, non-voided only.
   Response and Z-report show expected, declared, variance, totals by method, movements list.
2. Payment recording per `07-backend-architecture.md §9`. `external_reference` normalised
   (trim, upper, strip spaces). Cash: `tendered ≥ amount`, `change = tendered − amount`, both stored.
   Response includes `balance_pesewas` after this payment and `change_pesewas` large enough to display.
3. Settlement inside the same handler: balance 0 → `SESSION_SETTLED` + `ORDER_CLOSED` per SERVED order.
   Unserved orders → 409 `unserved_orders` **before** anything is recorded.
4. Payment void (authorisation, purpose `PAYMENT_VOID`): recompute `paid`; if the session was settled,
   emit `SESSION_REOPENED` and `ORDER_REOPENED` per closed order; both are flagged in the owner log.
5. Session reopen (authorisation, purpose `REOPEN`): same events, plus a Celery task `notify_owner_reopen`
   (email; WhatsApp is WS06's daily summary work) — stub the task so it logs in dev.
6. Drawer movements with authorisation (`DRAWER_MOVEMENT` purpose). `NO_SALE` has amount 0 and still writes an event.
7. `GET /bills/open` for the cashier screen: sessions not settled, with state chip, `bill_total`, `paid`,
   `balance`, table number, opened_at, order count.
8. Projector for `SESSION`/`SHIFT` events updating `table_sessions.paid_pesewas/settled_at/reopened_count`,
   `shifts.*`, `payments`, `drawer_movements`. Rebuildable; extend `verify_projections` to cover these tables.

## Tests required

- Split bill: three payments (cash, MoMo, card) totalling the bill → settled, all orders closed, one
  `SESSION_SETTLED`. Fourth payment → 422 `overpayment`.
- Partial: one payment less than total → not settled, chip `part_paid`.
- Cash change: tendered 30000 for amount 25500 → change 4500; tendered 20000 → 422 `tendered_insufficient`.
- Unserved order in session → 409, no payment recorded.
- Payment without open shift → 403 `shift_required`.
- Shift close variance: float 20000, cash payments 155000, paid out 10000, declared 163000 → expected 165000,
  variance −2000.
- Void payment after settlement → session reopened, orders SERVED again, events flagged.
- `verify_projections` clean after a scripted service including all of the above.

## Exit criteria

A scripted dinner service (fixture `service_script.py`, 20 tables, mixed methods, two voids, one reopen)
produces a Z-report whose numbers reconcile by hand from the fixture.
