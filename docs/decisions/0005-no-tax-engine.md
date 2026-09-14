# ADR-0005 — No tax engine. The system records what was charged.

**Status:** Accepted · 2026-09-14
**Supersedes:** the tax-inclusive design in the original research document.

## Context

Research into the Ghanaian environment (see `../05-operating-context-ghana.md`) established that a
VAT-registered restaurant in Ghana faces four statutory lines — NHIL 2.5%, GETFund 2.5%, Tourism
Levy 1%, VAT 15% — and that since January 2026 the GRA operates **E-VAT as a clearance system**: an
invoice is not legally valid until the GRA's Virtual Sales Data Controller validates it and returns
an Invoice Reference Number, a digital signature and a QR code.

The initial architecture modelled all of that: date-effective `tax_rules`, frozen `order_tax_lines`,
gapless `fiscal_invoices`, a pluggable `FiscalProvider`, and an offline invoice queue with
pre-fetched GRA signature keys.

The client's instruction is explicit: **do not handle VAT in the app — record how much was sold so
the owner knows what he is making.**

## Decision

The system performs **no tax calculation of any kind**.

- Menu prices are **what the guest pays**. Nothing is added at checkout.
- `order_total = Σ line_total − discounts`. That is the entire money calculation in the product.
- No tax lines on any screen, any receipt, or any report.
- No GRA E-VAT integration: no clearance call, no IRN, no fiscal QR code, no signature keys.
- No `tax_rules`, `order_tax_lines` or `fiscal_invoices` tables.

## Rationale

The instruction is the client's, and it is also the right engineering call:

1. **The restaurant is the taxpayer; this software is not.** RENZY's statutory invoicing is the
   owner's arrangement with the GRA. What we are building is an internal operations tool — a clean
   product boundary, not a gap.
2. **The clearance call was the single largest schedule and reliability risk in the project.** It put
   a synchronous dependency on a government server inside the payment path, and a government
   onboarding process — which nobody here controls — on the critical path to go-live.
3. **Everything the owner is actually paying for survives intact.** Every theft pattern in
   `01-product-spec.md §1` — unrung orders, post-payment voids, phantom discounts, drawer variance —
   is detectable without a single tax line.
4. **Scope discipline on a first paid build.** Weeks of compliance work removed from a project whose
   real risk is shipping late.

## Consequences

**The one that matters.** Ghanaian menu prices are tax-inclusive — the price on the menu is what the
guest hands over. So the figure this system reports is **gross cash through the till**. If RENZY is
VAT-registered, roughly one sixth of it already belongs to the GRA and the GTA, before cost of goods,
wages or rent.

Therefore:

- The database column is **`money_taken_pesewas`**, not `revenue`.
- The UI label is **"Money taken"** or **"Total collected"**, never "Revenue" and never "Profit".
- **Do not rename these.** An owner who reads gross as income makes bad decisions off a screen we
  built, and the naming is the only guard rail left once the tax lines are gone.

Other consequences:

- Receipts produced by this system are **sales records, not VAT invoices**. Do not describe them as
  invoices in the UI or in client-facing material.
- The owner must be told plainly, once, in writing: this system does not produce GRA-compliant
  invoices and does not calculate or report tax.

## If it is ever added

Reversible without touching existing columns, because the append-only event log preserves every line
price exactly as charged, so history can be re-derived.

Adding it would mean: a `tax_rules` table with **date-effective** rates (Ghana restructured VAT on
1 January 2026 and will again — rates must never live in code), `order_tax_lines` frozen per order so
reprints reproduce history, `fiscal_invoices` with gapless numbering separate from order numbers, a
`FiscalProvider` interface with mock and GRA implementations, and an offline invoice queue honouring
the 24-hour transmission window.

Estimated 2–3 weeks plus GRA onboarding lead time. **Do not start it without an explicit instruction
from the client.**
