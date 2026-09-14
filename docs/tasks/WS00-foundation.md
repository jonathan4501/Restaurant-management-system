# WS00 — Foundation

**Goal:** the rails every other workstream runs on. After WS00 an agent cannot write a float, forget a
tenant filter, skip an idempotency key, mutate the event log, or bypass the command runner without a
test failing.

**Depends on:** nothing. **Blocks:** everything.

## Owns

`backend/config/`, `backend/apps/core/`, `backend/pyproject.toml`, `backend/Dockerfile`,
`backend/openapi.json`, skeleton models + first migration of every app, `infra/`, `.github/workflows/`,
`Makefile`, `frontend/` shell.

## Deliverables

1. **Tooling**: `pyproject.toml` (uv, Django 5.2, DRF, drf-spectacular, psycopg 3, redis, celery,
   argon2-cffi, django-otp, PyJWT, uuid6, sentry-sdk, hypothesis, pytest-django, factory-boy, ruff, black,
   mypy). `Makefile` targets from `07-implementation-plan.md §5`. `infra/compose.yml`, `compose.dev.yml`,
   `Caddyfile`, `.env.example`.
2. **`apps/core`**: `uuid7.py`, `money.py` (`PesewasField`), `tenancy.py`, `business_date.py`,
   `errors.py` (problem+json handler + `ErrorCode`), `idempotency.py` + `IdempotencyKey` model,
   `commands.py` (`CommandContext`, `EventDraft`, `CommandOutcome`, `run_command`), `views.py`
   (`CommandView`, `RolePermission`), `projections.py` (registry), `publisher.py`, `admin.py` (`TenantAdmin`),
   `middleware.py` (request id + tenant context), `tests/test_invariants.py`.
3. **`apps/accounts`**: `Restaurant`, `Staff`, `Device` models + migration + admin; `principals.py`
   (`Principal`, `resolve_principal(headers)`, `DeviceStaffAuthentication` verifying device token + staff
   JWT). Token *issuance* is WS01. `manage.py seed_renzy` (restaurant, 12 tables, 5 staff with PINs, menu
   from the prototype data), `manage.py enrol_device`, `manage.py set_pin`.
4. **`apps/orders`**: `OrderEvent` model + migration `0001`, `0002_append_only_trigger`; `events.py`
   (full vocabulary from `03-data-model.md`, one payload dataclass each); `state_machine.py` (complete
   `TRANSITIONS` table); `projector.py` (registry hooks, empty handlers); `management/commands/
   rebuild_projections.py`, `verify_projections.py` (working for `OrderEvent` replay, projectors filled by WS03).
   `Order`, `OrderItem`, `OrderCounter` models + migration.
5. **`apps/menu`, `apps/floor`, `apps/payments`, `apps/reporting`, `apps/printing`**: models + migration
   `0001` matching `03-data-model.md`. No views yet.
6. **`apps/realtime`**: `GET /stream` and `GET /events` working end-to-end (they only need `OrderEvent`).
   A test that appends two events through `run_command` with a trivial handler and asserts they arrive on
   the stream, and that reconnecting with `Last-Event-ID` replays the second one only.
7. **OpenAPI**: drf-spectacular wired at `/api/schema/`; `openapi.json` committed; `make openapi` drift check.
8. **Frontend shell**: Next.js 15 + TS strict + Tailwind; `lib/api/client.ts` (openapi-fetch wrapper injecting
   headers + `Idempotency-Key`), `lib/api/schema.d.ts` generated, `lib/money.ts` (`formatPesewas`),
   `lib/outbox/types.ts`, route stubs `/login /order /kds /cashier /owner`. Vitest configured with one test
   for `formatPesewas`.
9. **CI**: `ci.yml` (Postgres + Redis services; `make check`; `npm run lint && npm run typecheck && npm test`), `deploy.yml`
   skeleton (SSH, `docker compose pull && up -d && migrate`).

## Exit criteria

- `docker compose -f infra/compose.dev.yml up` then `make migrate seed test` green on a clean clone.
- `test_invariants.py` passes and would fail if: a `FloatField` is added; a model lacks `restaurant`;
  a `POST` route is not a `CommandView`; `UPDATE order_events` is attempted.
- The `run_command` test proves: replay with same key returns identical body + `Idempotent-Replayed`;
  same key different body → 422; two restaurants' `seq` are independent and gapless.
- `curl -N /api/v1/stream` shows events published by the test handler; `Last-Event-ID` replay works.
- `openapi.json` matches `make openapi` output; `schema.d.ts` matches `make types`.

## Out of scope

PIN login endpoint, any order command handler, any UI beyond stubs, print bridge, Sentry wiring
(WS13), Celery tasks (WS06).
