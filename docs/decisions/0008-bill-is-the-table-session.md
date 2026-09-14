# ADR-0008 — The bill is the table session; payments settle the session

**Status:** Accepted · 2026-09-14
**Refines:** ADR-0006

## Context

`01-product-spec.md` says: *"Orders belong to a table session, not a person. A session accumulates
several rounds — drinks, then starters, then mains, then one more beer — and ends in one bill."* and
*"A bill stays open until fully settled. Partial payments accumulate against it."*

The first draft of `03-data-model.md` attached `payments.order_id NOT NULL` and closed an **order** when
`Σ payments ≥ order.total`. With several rounds per table that leaves the cashier settling four separate
orders for one party, and "four friends paying their share" has no natural home: their shares are amounts
against the table, not against particular rounds.

## Decision

**The bill is the table session.**

- `payments.session_id UUID NOT NULL`. `payments.order_id` is nullable and set only when the cashier
  explicitly pays one round (a rare case: a guest who leaves early and pays for their own round).
- Bill total = Σ `total_pesewas` of the session's non-voided orders.
- Balance = bill total − Σ non-voided payments.
- A payment may not exceed the outstanding balance. Cash is `tendered − change = amount`.
- When balance reaches zero the runner appends `SESSION_SETTLED` and then `ORDER_CLOSED` for every
  `SERVED` order in the session, in one transaction. Orders still `SUBMITTED`/`PREPARING`/`READY` block
  settlement — food that has not been served cannot be paid for and closed, because the owner's
  "no ticket closes without food leaving" rule would break.
- `SESSION_CLOSED` (the table is free) follows settlement, or follows a void of every order in the session.
- **Reopen** (`ORDER_REOPENED` in the vocabulary, manager PIN + reason, alerts owner) reopens the
  **session**: `closed_at` cleared, each closed order returns to `SERVED`, and new rounds can be added.
  Existing payments stay attached; the balance is recomputed.

Split bills are therefore **amount splits** against one bill, recorded as several payments with possibly
different methods. Item-level splitting ("I only had the tilapia") is out of scope for v1: the cashier
reads the bill and takes the amount each guest says. This matches how the restaurant operates today.

## Consequences

- `orders.status = CLOSED` is a consequence of session settlement, not of a payment on that order. The
  order state machine in `CLAUDE.md` is unchanged; only *what triggers* `pay` changes.
- Partial payments, split-by-amount and multi-round tables work from Phase 1 with no data migration later.
- Phase 1 typically has one round per table; the model costs nothing extra there.
- The Z-report and drawer variance are unaffected: every cash payment still belongs to a shift.
- A gateway integration later (ADR-0006) still adds only nullable provider columns to `payments`.

## Revisit when

The owner asks for item-level splits. That is a UI allocation problem on top of this model
(`payment_allocations(payment_id, order_item_id, amount_pesewas)`), not a reversal of it.
