# 05 — Operating context: Accra, Ghana

Two parts. **§1 changes the code.** §2 is background that was researched, considered, and
**deliberately excluded from v1** — it is recorded so the decision is not accidentally reversed by
someone who reads about it later and assumes it was an oversight.

---

## 1. Physical reality — this shapes the design

Architecture that ignores the room it runs in is fantasy.

| Reality | What the code or the install must do |
|---|---|
| **Power cuts are routine** | Tablets and phones carry their own battery. The router, the print bridge and the kitchen display need a **UPS** (650VA line-interactive, ≈ GH₵ 900). Not optional. |
| **Fixed broadband is unreliable; mobile data is not** | Use a **dual-SIM 4G/5G router with automatic failover** (MTN primary, Telecel backup) rather than fibre alone. Cheaper and more reliable than redundant fixed lines. |
| **Internet outages of 10–60 minutes are normal** | The system takes orders and serves food with **zero connectivity**. The kitchen never stops. This is why the PWA has a durable outbox — see `02-architecture.md §6`. |
| **High staff turnover in hospitality** | The UI must be learnable in ten minutes with no manual. PIN login, large targets, no nested menus. If training takes an hour, it will not happen. |
| **Devices get dropped, splashed and stolen** | Cheap Android tablets in rugged cases, not iPads. Every device enrolled and revocable from the back office. Budget to replace roughly one a quarter. |
| **Guests expect paper** | A thermal receipt printer is part of the install, not an upsell. |
| **English, Twi and Ga are all spoken** | English UI is fine for staff. A Twi toggle on the guest-facing screen is cheap and lands well with the owner. |
| **The developer is in Lomé, ~190 km away, across a border** | Everything remotely deployable, debuggable and recoverable. No hand-maintained stateful box inside the restaurant. This constraint outranks elegance — see `02-architecture.md §1`. |
| **Cash-heavy, with mobile money close behind** | Payment recording must be two taps. Cash change calculation must be large and unambiguous. MoMo references are typed by a tired cashier — keep the field forgiving. |

---

## 2. Tax and fiscal environment — researched, and OUT of scope

> **Read this before "helpfully" adding tax handling.** Its absence is a decision, not a gap.
> See `decisions/0005-no-tax-engine.md`.

### What Ghana requires of a VAT-registered business

Correct as of research in September 2026. Verify before acting on any of it.

**VAT structure changed on 1 January 2026** under the Value Added Tax Act, 2025 (Act 1151) and the
COVID-19 Health Recovery Levy (Repeal) Act, 2025:

- VAT remains **15%**.
- NHIL **2.5%** and GETFund **2.5%** were **decoupled** — they are no longer added to the base before
  VAT. All three are now computed on the **same net value**, giving a **20% effective rate**
  (previously 21.9% under cascading rules with the now-abolished 1% COVID levy).
- The **VAT Flat Rate Scheme was scrapped**.
- Registration threshold for **goods** rose to GH¢750,000. For **services** — which includes
  restaurants — registration is **mandatory regardless of turnover**.
- NHIL and GETFund became deductible as input tax.

Worked example on a GH¢1,000 net supply: NHIL 25 + GETFund 25 + VAT 150 = **GH¢1,200**.

**A separate 1% Tourism Development Levy** applies to restaurants and catering centres under the
Tourism Act, 2011 (Act 817), collected for the Ghana Tourism Authority.

**E-VAT is a clearance system, not a reporting one.** Since January 2026 an invoice is not a legally
valid VAT invoice until the GRA's Virtual Sales Data Controller validates it and returns an Invoice
Reference Number, a digital signature and a QR code. Offline stamping is permitted with GRA-issued
signature keys, with transmission required within 24 hours. Non-compliance penalties run to the
higher of GH¢50,000 or three times the tax involved.

### Why none of that is in this system

1. **The restaurant is the taxpayer, not this software.** RENZY's statutory invoicing is the owner's
   arrangement with GRA. This is an internal operations tool.
2. **The clearance call is the single biggest schedule risk in the project** — a synchronous
   dependency on a government server sitting inside the payment path, plus an onboarding process
   nobody here controls. Removing it removes the critical path.
3. **Scope discipline on a first paid build.** Everything in §1 of `01-product-spec.md` — the theft
   patterns the owner is actually paying to see — is deliverable without a single tax line.

### The one consequence to hold on to

Ghanaian menu prices are **what the guest pays** — tax-inclusive. So the figure this system reports is
**gross cash through the till**. If RENZY is VAT-registered, roughly one sixth of it already belongs
to GRA and the GTA before any cost of goods, wages or rent.

**This is why the field is called `money_taken_pesewas` and the UI label is "Money taken", never
"Revenue" and never "Profit".** An owner who reads gross as income makes bad decisions off a screen
we built. Keep the name.

### If it is ever added

The append-only event log preserves every line price as charged, so a tax layer can be computed
retroactively over stored history. Adding it means new tables (`tax_rules` with date-effective rates,
`order_tax_lines` frozen per order, `fiscal_invoices` with gapless numbering), a pluggable
`FiscalProvider` interface, and an offline invoice queue — **not** a change to any column that exists
today. Rates must live in a date-effective table, never in code: Ghana restructured VAT on
1 January 2026 and will do so again.

---

## Sources

- [Crowe Ghana — VAT Reform 2026](https://www.crowe.com/gh/news/ghana-vat-reform-2026)
- [Ghana Revenue Authority — VAT](https://gra.gov.gh/domestic-tax/tax-types/vat/)
- [GRA — Guidelines on the Certified Invoicing System (E-VAT), PDF](https://gra.gov.gh/wp-content/uploads/2024/07/E-VAT-GUIDELINES_20240222.pdf)
- [GRA E-VAT API v7.0 — Postman](https://documenter.getpostman.com/view/20074551/2s8Z76xVYR)
- [Deloitte Ghana — electronic invoicing regime, implementation update](https://www.deloitte.com/gh/en/services/tax/perspectives/electronic-invoicing-regime-update-on-implementation.html)
- [Ghana News Agency — the 1% tourism levy](https://gna.org.gh/2023/01/one-percent-tourism-levy-what-you-need-to-know/)
- [GhIPSS — GhQR universal QR scheme](https://ghipss.net/services/real-time-payments/ghana-s-universal-qr-code)

*Research, not tax advice. Anything acted on should be confirmed with a Ghanaian tax practitioner.*
