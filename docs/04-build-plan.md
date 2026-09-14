# 04 — Build plan

Each phase has an exit condition written in terms of what happens **in the restaurant**, not what is
merged. A phase is not done because the code exists.

---

## Phase 0 — Demo · complete

Clickable prototype, four stations, sample data. Purpose: close the deal and extract requirements
from the owner's reactions. Watch what he pokes at — that is the real spec.

---

## Phase 1 — The core loop · 3–4 weeks

Staff PIN auth · device enrolment · menu and categories via Django admin · table sessions ·
waiter ordering · SSE fan-out · kitchen display with age timers · cashier close-out recording
cash and mobile money · receipt printing · the event log · a first owner dashboard.

**Exit:** one full dinner service runs on the system, with paper pads kept as a backup nobody had
to reach for more than twice.

## Phase 2 — Make it survivable · 2–3 weeks

Offline PWA and IndexedDB outbox · idempotency end to end · modifiers and modifier groups ·
86'ing · voids and discounts behind a manager PIN with reason codes · split bills and partial
payments · shifts, drawer counts and Z-reports · Sentry · uptime alerts.

**Exit:** staff stop reaching for the paper pad at all, and a 30-minute internet cut passes without
anyone in the restaurant noticing.

## Phase 3 — Owner value · 2 weeks

The variance panel as the landing screen — voids after cooking, discounts and comps by staff member,
reopened bills, cash variance by shift · money taken by hour and day-part · best sellers by value ·
station timing · a daily summary pushed to the owner by WhatsApp or email at close.

**Exit:** the owner opens the dashboard without being prompted, and asks a question he could not have
asked before.

## Phase 4 — Depth · scope after Phase 3 ships

Course firing · recipes and stock deduction per sale · low-stock alerts · staff performance ·
guest QR ordering on their own phones · bar as a separate display.

## Phase 5 — Product · only after 60 stable days at RENZY

Multi-restaurant onboarding, per-tenant configuration, subscription billing, self-serve setup.
Do not start this on the strength of one customer's enthusiasm.

---

## Schedule reality

**9–12 weeks part-time for Phases 1–3, or 6–7 weeks full-time.**

Quoting three weeks means being wrong, burning weekends, and shipping quality as the thing that
gives. Quote twelve and deliver in ten.

---

## Commercial structure

- **Build fee against a signed scope, 50% up front.** Non-negotiable — it filters out clients who
  will not pay.
- **Monthly retainer** for hosting, backups, updates and a defined support window. This is where the
  actual business is. A one-off build is a job; a retainer is an asset.
- **"Scope change = new quote" in writing before starting.** Restaurant owners have ideas at 22:00
  on Saturdays.

---

## Running costs

| Item | USD / month |
|---|---|
| VPS | 6–12 |
| Managed PostgreSQL | 15–20 |
| Object storage | 1–3 |
| Domain + Cloudflare | 1 |
| Sentry, uptime | 0 (free tiers) |
| **Total** | **≈ 25–36** |

Hardware is a one-off the owner pays for: tablets, a kitchen display, two thermal printers, a
Raspberry Pi bridge, a dual-SIM 4G router with failover, and a UPS. Roughly GH₵ 18,000 all in —
verify locally, and settle **who pays for it** before quoting anything else.
