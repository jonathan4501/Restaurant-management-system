# 06 — Implementation plan

How the system in `01`–`05` gets built, by whom, in what order. Written for AI coding agents and
humans alike. `CLAUDE.md` is binding; this document is the schedule and the map.

Companion documents: `07-backend-architecture.md` (how the backend is put together, module by module),
`08-api-contract.md` (every endpoint, header and error), `tasks/` (one work package per workstream).

---

## 1. Repository layout (monorepo)

```
backend/                     Django 5.2 + DRF on ASGI · Python ≥ 3.12 · uv
  config/                    settings/{base,dev,test,prod}.py · asgi.py · urls.py · celery.py
  apps/
    core/                    tenancy, uuid7, PesewasField, idempotency, command runner, errors,
                             business_date, invariant tests            ← everything else depends on this
    accounts/                Restaurant, Staff, Device · PIN / device / owner / guest auth · manager authorisation
    menu/                    categories, items, modifier groups, modifiers, 86 / restore
    floor/                   tables, table sessions (the bill), QR tokens
    orders/                  event store, state machine, order commands, projector, rebuild / verify
    payments/                shifts, payments, drawer movements, settlement, Z-report
    realtime/                SSE stream, Redis publisher, polling fallback
    reporting/               daily_sales rollup, variance / today / patterns, event log endpoint
    printing/                ESC/POS payload builders (ticket, receipt) — consumed by bridge/
  tests/                     shared fixtures and factories
  openapi.json               generated, committed, drift-checked in CI
frontend/                    Next.js 15 App Router PWA · TypeScript strict · Tailwind · pnpm
bridge/                      Raspberry Pi print daemon (Python)
infra/                       compose.yml · compose.dev.yml · Caddyfile · .env.example · deploy.sh
.github/workflows/           ci.yml · deploy.yml
docs/                        you are here
```

Rule: an app never imports from another app's `views`/`serializers`; it may import models,
`events`, and `commands`. Cross-app writes go through the command runner, never through the ORM.

---

## 2. Workstreams

One agent per workstream, on branch `ws/NN-name`, merged to `main` by pull request. Each workstream has a
task file in `docs/tasks/` that is self-contained: goal, dependencies, owned paths, endpoints, events,
required tests, exit criteria, and what is out of scope.

| WS | Name | Depends on | Phase | Owns |
|---|---|---|---|---|
| 00 | Foundation | — | 1 | `core/`, skeleton of every app, `infra/`, CI, `openapi.json`, frontend shell |
| 01 | Accounts & auth | 00 | 1 | `accounts/` |
| 02 | Menu | 00 | 1 | `menu/` |
| 03 | Orders core | 00 01 02 | 1 | `orders/`, `floor/` |
| 04 | Realtime | 03 | 1 | `realtime/` |
| 05 | Payments & shifts | 03 | 1–2 | `payments/` |
| 06 | Reporting | 03 05 | 3 | `reporting/` |
| 07 | Frontend shell + ordering | 00 (mock) 02 03 | 1 | `frontend/` except the station folders below |
| 08 | Kitchen display | 04 07 | 1 | `frontend/app/kds/` |
| 09 | Cashier | 05 07 | 1–2 | `frontend/app/cashier/` |
| 10 | Owner back office | 06 07 | 3 | `frontend/app/owner/` |
| 11 | Offline outbox + service worker | 07 | 2 | `frontend/lib/outbox/`, `frontend/sw/` |
| 12 | Print bridge | 04 | 1 | `bridge/`, `backend/apps/printing/` |
| 13 | Infra, CI/CD, backups, Sentry, uptime | 00 | 1–2 | `infra/`, `.github/` |

### Critical path

```
WS00 ─► WS01 ─┐
      ─► WS02 ─┼─► WS03 ─► WS04 ─► WS08 (KDS)      ─► WS12 (print)
               │        └► WS05 ─► WS09 (cashier) ─► WS06 ─► WS10 (owner)
      ─► WS07 (frontend shell, against openapi.json + mock) ─► WS11 (offline)
      ─► WS13 (infra) runs alongside everything
```

WS03 is the bottleneck: it defines the command surface everything else calls. Its task file is the
most detailed. WS01, WS02, WS07 and WS13 run in parallel the moment WS00 merges.

### Mapping to the phases in `04-build-plan.md`

| Phase | Workstreams | Exit condition (from the build plan) |
|---|---|---|
| 1 — Core loop | 00 01 02 03 04 05(shift + single payment) 07 08 09(basic) 12 13(deploy) | One full dinner service on the system |
| 2 — Survivable | 05(split, drawer, Z-report) 09(full) 11 13(Sentry, uptime, backups) + modifiers/86/voids already in 02/03 | 30-minute internet cut passes unnoticed |
| 3 — Owner value | 06 10 + daily summary task | Owner opens the dashboard unprompted |

---

## 3. How agents work in this repository

Read `docs/tasks/00-agent-brief.md`. In short:

1. Read `CLAUDE.md`, then your `WS-NN.md`, then `07` and `08`. Start.
2. Stay inside the paths your workstream owns. Need a change elsewhere? Describe it in your PR;
   do not make it.
3. Every write goes through the command runner in `apps/core/commands.py`. No direct writes to
   projection tables. No `DELETE`. No floats.
4. `make check` (or its Docker equivalent) must be green before every commit: ruff, black, mypy,
   pytest including the invariant suite, OpenAPI drift.
5. Conventional commits tagged with the workstream: `feat(ws03): submit assigns order number`.
6. `docs/prototype/renzy-demo.html` is a **visual** reference only. Its totals include tax lines,
   it logs a fake GRA event, and it hard-deletes voided orders — all three predate ADR-0005/0001.

---

## 4. Testing strategy

| Layer | What | Where |
|---|---|---|
| Invariants | No `FloatField`/`DecimalField`; every model has `restaurant`; every `POST` requires `Idempotency-Key`; no `unscoped()` outside the allow-list; `order_events` rejects `UPDATE` | `backend/apps/core/tests/test_invariants.py` — runs in every workstream |
| Unit | State machine exhaustive over (status, command); totals property-based (hypothesis); `business_date`; idempotency semantics | per app `tests/` |
| Integration | command → event → projection → publish; replay by `seq`; tenant isolation (two restaurants, cross-tenant read is 404) | per app, real Postgres + Redis (CI services) |
| Contract | `openapi.json` regenerated equals committed | CI |
| Frontend | Vitest for outbox, money formatting, state chips; Playwright smoke per station against a Prism mock of `openapi.json` | `frontend/` |
| Field | The phase exit conditions in `04-build-plan.md` | the restaurant |

Rule from `CLAUDE.md`: every state transition and every money calculation has a test. UI polish does not.

---

## 5. Local development

```
cp infra/.env.example infra/.env
docker compose -f infra/compose.dev.yml up -d db redis
cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py seed_renzy
uv run uvicorn config.asgi:application --reload            # API on :8000
cd ../frontend && pnpm install && pnpm dev                 # PWA on :3000
```

`make` targets (run from the repo root; on Windows use the commands inside the Makefile or run them in
the `api` container with `docker compose exec api make <target>`):

| Target | Does |
|---|---|
| `make up` | compose up dev stack |
| `make migrate` / `make seed` | migrations / seed RENZY data |
| `make test` | pytest with coverage |
| `make check` | ruff + black --check + mypy + pytest + openapi drift |
| `make openapi` | regenerate `backend/openapi.json` |
| `make types` | regenerate `frontend/lib/api/schema.d.ts` |

---

## 6. Definition of done for a workstream

- Every exit criterion in the task file demonstrably met, with a test or a documented manual check.
- `make check` green; no new `# type: ignore` in money or state-transition code.
- `openapi.json` and `schema.d.ts` regenerated if any endpoint changed.
- No new dependency without a one-line justification in the PR.
- The PR description lists any request for changes outside the owned paths.
