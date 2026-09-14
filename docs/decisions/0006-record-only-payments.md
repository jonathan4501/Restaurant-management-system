# ADR-0006 — Payments are recorded, not processed

**Status:** Accepted · 2026-09-14

## Context

RENZY takes cash, mobile money (MTN MoMo, Telecel Cash, AirtelTigo Money) and some card. Ghana has
capable gateways — Hubtel, Paystack, Flutterwave, expressPay — and GhIPSS runs **GhQR**, a universal
interoperable QR scheme that works across every bank and wallet in the country.

## Decision

v1 **records** payments. The cashier selects a method and enters the amount; for mobile money they
key the transaction reference. The system calculates change for cash and attaches every payment to
the open shift. **No gateway is called.**

## Rationale

- No merchant onboarding delay on the critical path.
- No webhook reliability engineering, no settlement reconciliation, no refund flows.
- No PCI surface, and no gateway fee on every cedi the restaurant takes.
- It matches how the restaurant already operates, so staff training is "tap the button you already
  think in".
- It ships weeks sooner, which is the dominant constraint on a first paid build.

The trade accepted: the cashier can key a wrong amount or a wrong reference. That risk is contained
by the shift and drawer reconciliation in `01-product-spec.md §6` — a mis-keyed cash amount shows up
as variance at close, which is exactly the signal the owner bought the system for.

## Consequences

- `payments` already carries `method` and `external_reference`. A gateway integration adds
  `provider`, `provider_status` and `provider_payload` — **new nullable columns, no migration of
  existing data**.
- A bill supports several payments, so split bills and partial settlement work from day one and do
  not need revisiting when a gateway arrives.
- Reconciliation against MoMo statements is manual in v1. Say so to the owner rather than letting him
  assume otherwise.

## Revisit when

The owner asks for automatic reconciliation, or mis-keyed references become a recurring complaint.

At that point: **Paystack** for API quality or **Hubtel** for local depth — and separately, a
**static GhQR merchant code** on the table tents and receipts. GhQR costs essentially nothing to
operate, works with every wallet and bank in Ghana, and guests already know how to use it. It is the
cheapest payment improvement available and does not require this decision to be reversed.
