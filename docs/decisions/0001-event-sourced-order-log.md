# ADR-0001 — Orders are an append-only event log

**Status:** Accepted · 2026-09-14

## Context

The client's requirement includes: *"the owner can track sales, receipts, orders and every action
done by customers, kitchen and cashier."* The product's commercial value is anti-theft — voids,
discounts, comps and reopened bills must be provably intact.

A conventional mutable-row design satisfies "track orders" but makes "every action, provably" a
discipline problem: someone forgets to write an audit row, or a `DELETE` removes the evidence.

## Decision

`order_events` is the source of truth. Order state is a fold over its events, materialised into
projection tables (`orders`, `order_items`) for fast reads.

- `UPDATE` and `DELETE` are revoked on `order_events` at the database level.
- Every state change writes an event carrying `actor_id`, `actor_role`, `device_id`, and
  `authorised_by` where an override was approved.
- Projections are rebuildable from the log.

## Consequences

**Good**

- The audit trail exists by construction — you cannot forget to log, because logging *is* the write.
- Voids and comps are events, not deletions, so fraud reporting is trustworthy.
- Offline writes from independent devices have no conflict surface: append is commutative. This is
  what lets ADR-0002 avoid CRDTs entirely.
- "What happened to table 7 last Friday" is a query.
- Historical bills reprint exactly, because line prices were snapshotted at order time.

**Bad**

- Roughly 20–30% more backend code than mutable rows.
- Reports must read projections. Folding the log at query time will not scale and is banned.
- A projection bug can diverge from the log; reconciliation tooling is needed eventually.

**Rejected alternative:** mutable `orders` rows plus a separate `audit_log` table. Cheaper, but the
audit log is then a side effect that can be skipped, and the two can disagree — which is exactly the
failure the product exists to prevent.
