# Restaurant Management System — RENZY

Order and sales management for **RENZY**, a restaurant in Shiashi, Accra, Ghana.

A guest orders on a tablet handed over by the server. The kitchen sees the ticket on a display and
cooks it. The cashier takes payment and closes the bill. The owner sees what was sold, by whom, and
every action anyone took along the way.

Built for one restaurant, structured to serve many.

---

## Start here

**If you are an AI coding agent: read [`CLAUDE.md`](CLAUDE.md) first.** It contains the binding
rules — money as integers, append-only events, idempotency, and the scope boundaries you must not
cross without being asked.

| Document | What it answers |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | The short, binding build rules |
| [`docs/01-product-spec.md`](docs/01-product-spec.md) | What it does, for whom, and why the owner is buying it |
| [`docs/02-architecture.md`](docs/02-architecture.md) | How it is put together, and the reasoning |
| [`docs/03-data-model.md`](docs/03-data-model.md) | The schema |
| [`docs/04-build-plan.md`](docs/04-build-plan.md) | Phases, exit conditions, costs |
| [`docs/05-operating-context-ghana.md`](docs/05-operating-context-ghana.md) | Why Accra changes the design |
| [`docs/06-design-prompts.md`](docs/06-design-prompts.md) | The design system and a prompt per screen |
| [`docs/07-implementation-plan.md`](docs/07-implementation-plan.md) | Repo layout, workstreams, critical path, how agents work |
| [`docs/08-backend-architecture.md`](docs/08-backend-architecture.md) | Command runner, tenancy, idempotency, event store, auth, SSE — module by module |
| [`docs/09-api-contract.md`](docs/09-api-contract.md) | Every endpoint, header, error code and the SSE envelope |
| [`docs/tasks/`](docs/tasks/) | The agent brief and one work package per workstream (WS00–WS13) |
| [`docs/decisions/`](docs/decisions/) | Why X was chosen over Y |

## Running it locally

```
docker compose -f infra/compose.dev.yml up -d db redis     # Postgres on :5433, Redis on :6379
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py seed_renzy
uv run uvicorn config.asgi:application --reload            # API on :8000, docs at /api/docs/
cd ../frontend && npm install && npm run dev               # PWA on :3000
```

`make check` (or the same commands in the Makefile on Windows) runs everything CI runs.

---

## Stack

Next.js PWA (TypeScript) · Django 5 + DRF on ASGI · PostgreSQL · Redis · Celery ·
Server-Sent Events for realtime · Raspberry Pi ESC/POS print bridge · Docker Compose on a VPS.

## The rules that are expensive to break

1. **Money is an integer number of pesewas.** Never a float.
2. **Order lines snapshot their name and price.** Never join to the menu for history.
3. **`order_events` is append-only** and is the source of truth.
4. **Nothing is ever hard-deleted.**
5. **Every write is idempotent**, keyed by a client-generated UUIDv7.
6. **`restaurant_id` on every table and every query.**

Full detail and the reasoning behind each: [`CLAUDE.md`](CLAUDE.md).

## Explicitly not in v1

No tax or VAT calculation · no GRA E-VAT fiscal clearance · no payment gateway · no inventory ·
no delivery · no native apps.

The absence of tax handling is a **decision**, not an oversight — see
[`docs/decisions/0005-no-tax-engine.md`](docs/decisions/0005-no-tax-engine.md) before adding any.

The owner-facing sales figure is labelled **"Money taken"**, never "Revenue" or "Profit", because
Ghanaian menu prices are tax-inclusive and the number is gross cash through the till. Keep the name.
