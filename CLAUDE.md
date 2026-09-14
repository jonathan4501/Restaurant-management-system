# CLAUDE.md — build rules for this repository

Read this before writing any code. It overrides habit and general best practice.
Longer reasoning lives in `docs/`; this file is the short, binding version.

---

## What we are building

A restaurant order and sales system for **RENZY**, a restaurant in Shiashi, Accra, Ghana.

Four roles, one loop:

1. **Guest** orders on a tablet handed over by the server (or the server orders on their behalf).
2. **Kitchen** receives the ticket on a display, cooks, marks it ready.
3. **Cashier** sees it is ready, takes payment, marks it paid.
4. **Owner** sees sales, orders, and every action every person took.

v1 ships for RENZY only, but is **multi-tenant-ready**: `restaurant_id` on every table and every query.

---

## Scope boundaries — do not cross these without being asked

| Not in v1 | Why |
|---|---|
| **Any tax or VAT calculation** | Deliberate. The app records what was charged and collected. It does not compute, split, display or report NHIL, GETFund, Tourism Levy or VAT. See `docs/decisions/0005-no-tax-engine.md`. |
| **GRA E-VAT / fiscal invoice clearance** | Same decision. No IRN, no fiscal QR code, no clearance calls. |
| **Payment gateway integration** | Cashier records the tender manually. No Hubtel/Paystack/MoMo API calls. See `0006`. |
| **Inventory / stock control** | Phase 4 at the earliest. |
| **Delivery / takeaway** | Not confirmed with the client. Ask before modelling it. |
| **Native mobile apps** | The PWA is the app. See `0004`. |

If a task seems to need one of these, **stop and ask** rather than adding it.

---

## Non-negotiable invariants

These are the rules that are expensive to fix later. Treat a violation as a bug even if tests pass.

### 1. Money is an integer number of pesewas

```python
price_pesewas = 7500   # GH₵ 75.00   ✅
price = 75.00          # ❌ never
Decimal("75.00")       # ❌ not in the DB, not over the wire
```

`INTEGER` columns, integers in JSON, integers in every calculation. Format to `GH₵ x.xx` only at the
last moment, in the UI. Floats silently lose money and will not reconcile against a cash drawer.

### 2. Snapshot the name and price onto every order line

An order line stores `name_snapshot` and `unit_price_pesewas` copied from the menu item at the moment
of ordering. **Never join to `menu_items` to price or label a historical order.** Changing tomorrow's
price must not rewrite yesterday's bill.

### 3. Orders are an append-only event log

`order_events` is the source of truth. Current order state is a fold over its events, materialised into
projection tables for reads.

- Append only. `UPDATE` and `DELETE` are revoked on that table at the database level.
- Every state change writes an event. There is no other way to change an order.
- Every event records `actor_id`, `actor_role`, `device_id` and, where an override was authorised,
  `authorised_by`.

This is what gives the owner "every action by every person" for free, and makes it impossible to
change an order without leaving a trace.

### 4. Nothing is ever hard-deleted

Voids, cancellations, removed menu items, retired staff, revoked devices: set `voided_at`,
`revoked_at`, `is_active = false`. Never `DELETE`.

### 5. Every write is idempotent

Client generates a **UUIDv7** for the entity and sends `Idempotency-Key: <uuid>` on every command.
The server has `UNIQUE (restaurant_id, idempotency_key)` and returns the original response on replay.

A waiter double-tapping "Send" on a slow connection must not produce two tickets. This is enforced by
construction, not by disabling the button.

### 6. Server timestamps are authoritative

Store the client's claim as `client_created_at` for the audit trail. Order, sort and report on the
server's `created_at`. Never trust a device clock for anything that matters.

### 7. `restaurant_id` on every table and every query

Enforce it in a base queryset manager or equivalent, not by remembering to add a filter.
A missing tenant filter is a data leak, not a bug.

### 8. Manager PIN + reason code for anything that moves money

Required for: voiding after the kitchen acknowledged the order, any discount or comp, price override,
reopening a closed bill, cash-drawer no-sale, editing a menu price during service hours.

Each of these writes an event naming **both the actor and the authoriser**.

---

## Order state machine

Enforce server-side. Reject illegal transitions with a 409; do not silently coerce.

```
DRAFT ──submit──► SUBMITTED ──ack──► PREPARING ──ready──► READY ──serve──► SERVED ──pay──► CLOSED
                      │                  │                                    │              │
                      │                  └── void (MANAGER PIN + reason) ──┐   │              │
                      └── void (no PIN needed, nothing cooked yet) ────────┼───┘              │
                                                                          ▼                   │
                                                                       VOIDED                 │
                                        reopen (MANAGER PIN + reason, alerts owner) ──────────┘
```

Orders belong to a **table session**, not to a person. One session accumulates several order rounds
(drinks, starters, mains, one more beer) and produces one bill.

---

## Totals

There is exactly one money calculation in this system:

```
line_total  = (unit_price_pesewas + sum(modifier prices)) * quantity
order_total = sum(line_total) - discounts
```

**Menu prices are what the guest pays.** No tax is added, split out, or displayed anywhere.

In the UI, the owner-facing figure is labelled **"Money taken"** or **"Total collected"** —
never "Revenue", never "Profit". It is gross cash through the till, and it is not the owner's income.
Do not rename it.

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) as a single installable **PWA**, TypeScript strict, Tailwind |
| Client state | TanStack Query + Zustand; **IndexedDB outbox** for offline writes (`idb`); Workbox service worker |
| Backend | **Django 5 + DRF**, ASGI (Uvicorn) |
| Realtime | **Server-Sent Events** over Redis pub/sub. Not WebSockets. See `0003`. |
| Database | **PostgreSQL**, managed instance |
| Async | Celery + Redis |
| Printing | Raspberry Pi bridge, ESC/POS over TCP:9100 |
| Hosting | VPS + Docker Compose. The SSE endpoint must **not** run on serverless. |
| Errors | Sentry from day one — nobody on the dev team is in the building when it breaks |

One ordering UI with a **mode flag**, not three apps:

- `waiter` — staff holds the device (default)
- `guest` — handed to the customer, token scoped to **one table session**, read menu + build draft only
- `qr` — customer's own phone via a table QR code

The `guest` and `qr` tokens are hostile-input surfaces. They must not expose other tables, other
bills, staff functions, or any total but their own.

---

## Conventions

- Python: `ruff` + `black`, type hints on anything touching money or state transitions.
- TypeScript: `strict: true`. No `any` in domain code.
- API types come from `drf-spectacular` → OpenAPI → `openapi-typescript`. Do not hand-write client types.
- Migrations are additive where possible. Never edit a migration that has run in production.
- Tests: every state transition and every money calculation has one. UI polish does not need one.
- Secrets in environment variables. Never in the repo, never in a migration, never in a fixture.

## Commit style

Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
Reference the phase where useful: `feat(kds): ticket age timer with 10/15 min thresholds`.

---

## Where to look

| Question | File |
|---|---|
| What does the system do, for whom? | `docs/01-product-spec.md` |
| How is it put together, and why? | `docs/02-architecture.md` |
| What are the tables? | `docs/03-data-model.md` |
| What do we build first? | `docs/04-build-plan.md` |
| Why does Accra change the design? | `docs/05-operating-context-ghana.md` |
| Who builds what, in what order? | `docs/06-implementation-plan.md` |
| How is the backend wired, module by module? | `docs/07-backend-architecture.md` |
| What are the endpoints, headers, errors? | `docs/08-api-contract.md` |
| What is my workstream's task? | `docs/tasks/00-agent-brief.md`, then `docs/tasks/WSNN-*.md` |
| Why was X chosen over Y? | `docs/decisions/` |

Note for agents: `docs/prototype/renzy-demo.html` is a **visual** reference only. It predates ADR-0005
and ADR-0001 — it computes tax lines, logs a fake GRA event and hard-deletes voided orders. Never copy its logic.
