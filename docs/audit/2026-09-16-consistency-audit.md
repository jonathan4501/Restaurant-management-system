# Consistency audit — `develop` against the binding docs

**Date:** 2026-09-16
**Audited commit:** `e3141f5` (`origin/develop`), with the bulk of the analysis performed on
`56cf02c`; the only change in between is 1 038 lines of new payments tests, re-checked and clean.
**Audited against:** `CLAUDE.md`, `docs/tasks/00-agent-brief.md`, `docs/01`–`docs/09`,
`docs/decisions/0001`–`0008`, all `docs/tasks/WS*.md`.
**Method:** read-only inspection of a clean `develop` worktree, plus ruff / black / mypy / pytest and
eslint / tsc / vitest run against it. Nothing was modified or refactored.

Merged workstreams on `develop`: WS00, WS01, WS02, WS03, WS04, WS05, WS05b, WS07, WS08, WS13.
In flight elsewhere and deliberately out of scope: WS06 (reporting), WS09 (cashier), WS10 (owner),
WS11 (outbox), WS12 (print bridge).

---

## 1. Summary verdict

**`develop` is trustworthy as a base to build on.** Every invariant that is expensive to fix later is
holding, and holding *by construction* rather than by discipline: money is integer pesewas
everywhere, `order_events` rejects `UPDATE`/`DELETE` at the database level, every model carries
`restaurant`, every `POST` route extends `CommandView`, `.unscoped()` stays inside its allow-list, and
manager authorisation is enforced for all eight money-moving actions. The mechanical checks in
`apps/core/tests/test_invariants.py` are doing exactly the job they were written to do.

All eight local build gates are green: ruff, black (150 files), mypy (120 files), pytest (346 passed at
`e3141f5`, 344 at `56cf02c`), eslint, `tsc --noEmit`, vitest (24 passed).

The problems are not in the domain logic. They are in the seam between backend and frontend, in the
verification pipeline, and in one missing document.

### Top 3 risks

1. **`npm run types` regenerates the API types from the wrong file.** `frontend/package.json`
   generates `lib/api/schema.d.ts` from the hand-written `frontend/mock/openapi.json`; the `Makefile`
   and CI generate it from `backend/openapi.json`. The two disagree on path parameter names
   (`/orders/{id}/items` vs `/orders/{order_id}/items`). Any developer or agent who follows the brief's
   instruction to "run `make openapi` and `make types`" will get a different result depending on which
   entry point they use, and one of the two silently reintroduces the drift that already broke CI once
   and needed an out-of-band `fix/frontend-real-backend` branch to repair.

2. **CI has never run on `develop`.** `ci.yml` triggers on `push` to `main` and on `pull_request`.
   Workstreams are merged into `develop` with direct pushes, so `gh run list --branch develop` returns
   nothing. Every merged workstream's last recorded CI result is from its own PR, and four of the five
   most recent runs in the repository are red. The integration branch that everything is built on has
   never been verified by the pipeline that is supposed to guard it.

3. **`docs/06-design-prompts.md` does not exist and never has.** `CLAUDE.md` names it twice as the
   binding source of design tokens ("`docs/06-design-prompts.md` carries the binding design tokens"),
   `docs/tasks/00-agent-brief.md` assumes it, and commit `9a2b3e0` renumbered the other plan docs
   specifically to sit "beside 06-design-prompts". `git log --all -- docs/06-design-prompts.md` is
   empty. Two UI workstreams (WS07, WS08) have shipped against a document that was never written, with
   only the four-line summary in `CLAUDE.md` to go on — and the touch-target violations in §2 are the
   predictable result.

---

## 2. Invariant violations

Severity: **HIGH** = will cost money or force rework; **MEDIUM** = breaks a stated rule with a
contained blast radius; **LOW** = cosmetic or latent.

### H1 — `npm run types` reads the mock schema, not the generated one · HIGH

`frontend/package.json:13`

```json
"types": "openapi-typescript ./mock/openapi.json -o lib/api/schema.d.ts",
```

`Makefile:43` and `.github/workflows/ci.yml:66` both generate the same output file from
`../backend/openapi.json`. `frontend/mock/openapi.json` is tracked, hand-maintained, and uses
`/api/v1/orders/{id}/items` where the backend emits `/api/v1/orders/{order_id}/items`.

This is the mechanism behind the CI failure on run `35027404015` (thirteen `tsc` errors, all of the
form `Argument of type '"/api/v1/orders/{id}/items"' is not assignable to parameter of type
'PathsWithMethod<paths, "post">'`). The code has since been corrected, but the generator that produced
the bad state is still wired up and still the one a developer reaches for.

*Suggested fix (do not apply):* point the `types` script at `../backend/openapi.json` so it matches the
`Makefile` and CI. Keep `mock/openapi.json` for `npm run mock` only, or better, run Prism against
`backend/openapi.json` as `docs/tasks/WS07-frontend-shell-ordering.md` §1 actually specifies
("`npm run mock` runs Prism on `../backend/openapi.json`") and delete the mock entirely.

### H2 — 17 of 39 `POST` operations have no schema, forcing hand-written types · HIGH

`backend/openapi.json` (generated), `backend/apps/orders/views.py`, `backend/apps/accounts/views.py:559`

`manage.py spectacular` completes with **108 errors (33 unique)** and 13 warnings, all of the form:

```
Error [SubmitOrderView]: unable to guess serializer. This is graceful fallback handling for APIViews.
```

Affected views include `AddItemView` (`views.py:67`), `RemoveItemView` (`:75`),
`ModifyItemView` (`:83`), `SubmitOrderView` (`:91`), `StartItemView` (`:107`), `ReadyItemView` (`:115`),
`ReadyOrderView` (`:123`), `ServeOrderView` (`:131`), `VoidOrderView` (`:139`), `DiscountView` (`:160`),
`CompView` (`:169`), `PriceOverrideView` (`:178`), `FireView` (`:187`), and
`GuestTokenView` (`accounts/views.py:559`). `TablesView` (`floor/views.py:33`) resolves to a
"generic free-form object".

The count in the generated file: 39 `post:` operations, 22 `requestBody:` blocks. `openapi-typescript`
therefore emits `requestBody?: never` / `content?: never` 67 times, and the frontend cannot call those
endpoints through the typed client. The workaround in the code is a cast:

| File:line | Cast |
|---|---|
| `frontend/app/login/page.tsx:44` | `data as unknown as DeviceMe` |
| `frontend/app/login/page.tsx:51` | `data as unknown as EnrolResponse` |
| `frontend/app/login/page.tsx:61` | `error as unknown as Problem` |
| `frontend/app/login/page.tsx:66` | `data as unknown as PinLoginResponse` |
| `frontend/app/guest/[qr_token]/page.tsx:23` | `data as unknown as QrEntryResponse` |
| `frontend/components/OrderScreen.tsx:87` | `data as unknown as { id?: string }` |
| `frontend/components/kds/KdsBoard.tsx:90` | `data as unknown as KdsTicket[]` |
| `frontend/components/kds/EightySixSheet.tsx:26` | `data as unknown as MenuResponse` |

The response shapes those casts assert are hand-written in `frontend/lib/domain.ts` (`DeviceMe`,
`MenuResponse`, `KdsTicket`, `TableRow`, `OpenSessionSummary`, and eleven more). `CLAUDE.md` is explicit:
"API types come from `drf-spectacular` → OpenAPI → `openapi-typescript`. Do not hand-write client
types." The letter of the rule is being followed — `schema.d.ts` is generated — but the generated types
are empty where it matters, so the substance of the rule is not.

*Suggested fix (do not apply):* add `@extend_schema` with request and response serializers to the
command views (they already have `input_serializer`; the response shape is the `CommandOutcome.response`
dict and needs an output serializer). Once the OpenAPI describes the bodies, the casts and most of
`lib/domain.ts` can be deleted. This is the single change that unblocks WS09, WS10 and WS11 from
repeating the same pattern.

### M1 — float division in a money path (uncommitted WS06 code) · MEDIUM

`backend/apps/reporting/queries.py:190` — untracked in the main checkout, on `ws/06-reporting`

```python
"average_bill_pesewas": round(money_taken / bills) if bills else 0,
```

`money_taken / bills` is a float. `round()` returns an int, so nothing escapes to the database, but
`CLAUDE.md` is unconditional: "If you write `float`, `Decimal` or `/ 100` outside `formatPesewas` and
the one rounding helper in `totals.py`, you have a bug." This is the only float in a money expression
anywhere in the codebase, tracked or not, and it should not be the precedent WS06 sets.

*Suggested fix (do not apply):* `money_taken // bills`, or route it through the existing rounding
helper in `apps/orders/totals.py` if banker's rounding is wanted. Catch it before `ws/06-reporting`
merges.

### M2 — staff touch targets below the 56 px minimum · MEDIUM

`CLAUDE.md`: "56px minimum touch targets on staff screens (64px for primary actions)". Tailwind
`min-h-14` is 56 px and `min-h-16` is 64 px, so the compliant sizes are in use in most places —
`PinPad`, `TicketCard`, `KdsBoard`, `EightySixSheet` and the login flow are all correct. The
exceptions:

| File:line | Class | Actual | Element |
|---|---|---|---|
| `frontend/components/DraftPanel.tsx:54` | `min-h-10 min-w-10` | 40 px | quantity decrement |
| `frontend/components/DraftPanel.tsx:58` | `min-h-10 min-w-10` | 40 px | quantity increment |
| `frontend/components/ModifierSheet.tsx:120` | `min-h-11 min-w-11` | 44 px | quantity decrement |
| `frontend/components/ModifierSheet.tsx:124` | `min-h-11 min-w-11` | 44 px | quantity increment |
| `frontend/components/ModifierSheet.tsx:65` | `min-h-11` | 44 px | close sheet |
| `frontend/components/OrderScreen.tsx:199` | `min-h-11` | 44 px | "Change table" |
| `frontend/components/AuthoriseSheet.tsx:60` | `min-h-11` | 44 px | close sheet |
| `frontend/components/MenuBrowser.tsx:33` | `min-h-11` | 44 px | category chips |
| `frontend/app/login/page.tsx:111` | `min-h-11` | 44 px | "← Back" |

The two 40 px steppers in `DraftPanel` are the worst of these: adjusting a quantity on a live order is
a frequent, one-handed, money-affecting action on a screen a waiter is holding.

*Suggested fix (do not apply):* raise all of these to `min-h-14 min-w-14`. Then write the rule down —
see R3 in §8 — because there is currently no document to check them against and no lint rule to catch
the next one.

### L1 — double-encoded UTF-8 renders as garbage on the order screen · LOW

`frontend/components/OrderScreen.tsx:186` and `:205`

```tsx
{tablesQuery.isLoading ? <p className="text-sm">Loading tablesâ€¦</p> : null}
{menuQuery.isLoading ? <p className="text-sm">Loading menuâ€¦</p> : null}
```

The ellipsis has been through a UTF-8 → CP1252 → UTF-8 round trip. A waiter on a slow connection sees
"Loading tables╬ª". `backend/config/settings/prod.py:2` has the same corruption in a docstring
(harmless, but the same cause). Every other file in the repo is clean UTF-8, so this is two files, not
a systemic encoding problem.

*Suggested fix (do not apply):* replace with a literal `…` or `...`, and check the editor's encoding on
whichever machine produced these two files.

### L2 — a `delete()` override exists on menu config models · LOW

`backend/apps/menu/models.py:18-25`

`MenuCacheInvalidatingMixin.delete()` wraps `super().delete()` to flush the menu cache. It performs no
delete of its own, and `TenantAdmin.has_delete_permission` (`apps/core/admin.py:38`) returns `False`, so
the path is closed in practice. Recording it because "Nothing is ever hard-deleted" is invariant 4, and
a reader skimming for `delete(` will find this and reasonably conclude that deleting menu rows is
sanctioned.

*Suggested fix (do not apply):* leave the code as is; add a one-line comment saying the override exists
only so that a delete performed outside the app (a `manage.py shell`, a data migration) does not leave
a stale cache, and that the admin refuses deletes.

### Invariants verified clean

Worth stating explicitly, because these are the ones that would be expensive:

- **Money is integer pesewas.** No `FloatField` or `DecimalField` on any model. The only `Decimal` in
  the codebase is `apps/orders/totals.py:40-41`, the sanctioned `ROUND_HALF_UP` percentage-discount
  helper. The only `/ 100` in shipped code is `frontend/lib/money.ts:15`, inside `formatPesewas`.
  `test_every_money_column_is_a_pesewas_field` additionally forces every `*_pesewas` column through
  `PesewasField`.
- **Snapshots.** `order_items` carries `name_snapshot`, `unit_price_pesewas`, `prep_station` and a
  `modifiers` JSONB snapshot; `apps/orders/projector.py:1` carries the docstring "never read
  menu_items" and does not.
- **Append-only event log.** Database trigger plus `test_order_events_rejects_update_and_delete`, which
  asserts that `UPDATE`, `DELETE` and `Model.save()` all raise.
- **No hard deletes.** `voided_at`, `revoked_at`, `settled_at`, `is_active` throughout;
  `TenantAdmin.has_delete_permission` is `False`; the only `.delete()` calls are Redis key expiry in
  `accounts/`, idempotency-row cleanup, and `rebuild_projections`.
- **Idempotency.** `test_every_post_route_is_a_command_view` runs over the live URL resolver with an
  **empty** allow-list and passes: all 39 POST routes extend `CommandView`, which rejects a missing or
  non-UUIDv7 `Idempotency-Key` with 400 `idempotency_key_missing`.
- **Server timestamps.** `CommandView.parse_client_time` stores the device clock as
  `client_created_at`; `_append_events` stamps `created_at` from `timezone.now()`; `seq` is assigned
  under `pg_advisory_xact_lock` per restaurant.
- **Tenant scope.** `test_every_model_has_restaurant` passes with only `accounts.Restaurant` exempt.
  `.unscoped()` appears only in the allow-listed files plus projectors and tests, which the test
  excludes by design because they filter `restaurant_id` explicitly — and they all do.
- **Manager PIN + reason.** All eight actions from `CLAUDE.md` §8 are covered:
  `DISCOUNT`, `COMP`, `PRICE_OVERRIDE` (`orders/views.py:163,172,181`), `DRAWER_MOVEMENT`,
  `PAYMENT_VOID`, `REOPEN` (`payments/views.py:94,149,164`), `PRICE_CHANGE_IN_SERVICE`
  (`menu/views.py:132`), and `VOID_AFTER_ACK` via `VoidOrderView.needs_authorisation`
  (`orders/views.py:143-154`) driven off the state machine. `apps/orders/commands/money.py` re-checks
  `ctx.authorised_by` under the row lock, so the unlocked status read in `needs_authorisation` cannot be
  raced into a PIN-free void.
- **Labels.** No occurrence of "Revenue" or "Profit" in any UI string, API description or column name.
  `daily_sales.money_taken_pesewas` carries the help text "Money taken — gross cash through the till.
  Not revenue." and `config/settings/base.py:150` puts the same phrase in the OpenAPI description.

---

## 3. Scope-boundary breaches

**None.** This is a clean result and worth recording as such.

- **Tax / VAT / GRA:** the only occurrences of `VAT`, `NHIL`, `GETFund`, `Tourism Levy`, `IRN` or
  `E-VAT` anywhere in the repository are in `docs/prototype/renzy-demo.html` (lines 440, 555-565,
  811-864) and in the ADRs and task files that forbid them. The prototype carries a warning header at
  lines 3-5 naming exactly what it gets wrong. No `tax_rules`, `order_tax_lines` or `fiscal_invoices`
  table; no tax field on any model; `order_total = subtotal − discount` is the only money calculation.
- **Payment gateway:** no `hubtel`, `paystack` or MoMo API client. `payments/commands.py` records the
  tender and normalises `external_reference` as free text (`normalise_reference`, line 77), which is
  precisely what ADR-0006 specifies.
- **Inventory:** no stock model, no stock field. The 86 switch is `menu_items.is_available`, a boolean.
- **Delivery / takeaway:** `orders.origin` is constrained to `WAITER | GUEST_TABLET | GUEST_QR`. Nothing
  else.
- **Native app:** no React Native, no Expo. `frontend/public/manifest.json` and the Workbox wiring are
  the PWA route ADR-0004 chose.

---

## 4. Contract, model and OpenAPI drift

### `backend/openapi.json` is in sync

Regenerating it against the audited tree produces a file whose lines are **identical** to the committed
one (0 differences by line comparison; an initial byte-level mismatch was a CRLF artifact of the
Windows working tree — `git ls-files --eol` confirms the index stores LF). The `backend` job of CI run
`35027404015` passes its "OpenAPI drift" step. `frontend/lib/api/schema.d.ts` also matches: CI's
"Generated types match openapi.json" step is green.

So there is no drift *today*. H1 in §2 is the reason it will not stay that way.

One format note: `backend/openapi.json` contains **YAML**, not JSON — `manage.py spectacular --file
openapi.json` defaults to YAML. `openapi-typescript` and Prism both accept it, so nothing is broken, but
anything that does `JSON.parse` or `json.load` on the file by its extension will fail.

### Endpoints implemented vs `docs/09-api-contract.md` §3

Every endpoint the merged workstreams own is present and at the documented path. Two are implemented
but **not documented**:

| Endpoint | Where | Note |
|---|---|---|
| `GET /auth/owner/me` | `accounts/urls.py:14` | owner session introspection; add to §3 "Auth and devices" |
| `GET /guest/sessions/{session_id}` | `accounts/urls.py:22-26` | guest session read; the contract lists only `POST /guest/sessions/{qr_token}` |

Documented but not yet built, all belonging to unmerged workstreams — expected, not drift:
`GET /reports/variance`, `GET /reports/today`, `GET /reports/patterns`, `GET /events/log` (WS06/WS10).
`POST /orders/{id}/fire` is registered and returns 501 exactly as §3 requires.

### Data model vs `docs/03-data-model.md`

Matches, including the 2026-09-14 amendments. Verified present: `order_counters` with the composite
primary key; `idempotency_keys` keyed `(restaurant_id, key)`; `drawer_movements`; nullable
`orders.order_number` assigned at submit under a counter row lock (`orders/commands/submit.py`);
`table_sessions.bill_total_pesewas / paid_pesewas / settled_at / reopened_count`;
`shifts.variance_pesewas` as a `GeneratedField`; the `order_events` `aggregate_type` check constraint
over the six aggregates; the flagged-set derivation in `orders/events.py` rather than a stored column.

### Documentation drift

| Issue | Severity |
|---|---|
| `docs/06-design-prompts.md` is cited as binding by `CLAUDE.md` and `00-agent-brief.md` but has never existed in git history | HIGH |
| `docs/09-api-contract.md:1` is titled "# 08 — API contract (v1)" — stale after commit `9a2b3e0` renumbered the plan docs | LOW |
| `frontend/mock/openapi.json` is a tracked second schema for the same API, disagreeing with the generated one on path parameter names | HIGH (same root as H1) |

---

## 5. Ownership and duplication notes

The agent brief permits duplication when an agent is blocked, provided it is recorded. Recording it.

### Ownership

- **WS08 wrote into WS07's paths.** `docs/tasks/WS08-kitchen-display.md` claims `frontend/app/kds/` and
  `frontend/lib/realtime/`. The branch also added `frontend/components/kds/` (three components),
  `frontend/lib/kds/urgency.ts` + its test, and `frontend/e2e/kds.spec.ts` — all inside WS07's
  "`frontend/` except `app/kds/`, `app/cashier/`, `app/owner/`, `lib/outbox/`, `sw/`". The code is good
  and the placement is arguably better than cramming it into `app/kds/`; the fix is to amend WS08's
  owned paths, not to move the files.
- **`table_sessions` is written by three apps.** `apps/floor/models.TableSession` is the WS03/floor
  aggregate, but its projection columns are maintained from `floor/projector.py` (`opened_at`,
  `closed_at`, `settled_at`, `reopened_count`), `orders/projector.py:17` (`bill_total_pesewas`) and
  `payments/projector.py:19` (`paid_pesewas`). Each writer is correct and each filters
  `restaurant_id` explicitly, but no single file tells you how a session's numbers are derived.
- **Report shaping lives in WS05.** `apps/payments/reports.py` contains `z_report`, `open_bills`,
  `serialize_shift` and `current_shift_for` — reporting logic in the payments app while WS06 owns
  reporting. Defensible (the Z-report is a cashier artefact, not an owner report), but see the
  duplication note below.
- **`PriceOverrideView.allowed_roles = COMP`** (`orders/views.py:179`) reuses the `COMP` role tuple for
  price override. The two role sets happen to be identical (MANAGER, OWNER), so behaviour is correct,
  but the next person to narrow one of them will silently change the other.
- **An out-of-band branch fixed a WS07 exit criterion.** `fix/frontend-real-backend` (merge `8725a90`)
  sits outside the `ws/NN-name` scheme and repaired the frontend's mock-vs-backend path mismatch. Not a
  violation of anything, but it means the workstream that owns those files did not make the fix, and the
  generator that caused it (H1) was left in place.

### Duplication

| Duplicated thing | Locations |
|---|---|
| Session-total refresh from a `Sum` aggregate into `table_sessions` | `orders/projector.py:17` `_refresh_session_bill`, `payments/projector.py:19` `_refresh_session_paid` — near-identical shape, neither beside the aggregate |
| "The caller's open shift" lookup | `payments/commands.py:61` `open_shift_for`, `payments/reports.py:114` `current_shift_for` |
| Business-date window derivation | `apps/core/business_date.py` (canonical), re-derived as `day_bounds` in the unmerged `apps/reporting/queries.py:42` |
| Staff id → name map | `payments/reports.py`, and again as `_staff_names` in the unmerged `apps/reporting/queries.py:34` |

The last two are in code that has not merged yet and are the cheapest to consolidate before WS06 lands.

---

## 6. Test and coverage gaps per workstream

`CLAUDE.md`: "every state transition and every money calculation has one."

Current totals: 143 backend test functions across 20 files, 346 tests after parametrisation, all
passing. 24 frontend tests across 4 files, all passing.

| Workstream | Coverage | Gap |
|---|---|---|
| WS00 core | `test_invariants` (7), `test_runner` (8), `test_command_view` (8), `test_tenancy` (4), `test_money` (3), `test_business_date` (3) | none material |
| WS01 accounts | `test_auth` (14), `test_principals` (9) | none material |
| WS02 menu | `test_menu_api` (6), `test_commands` (5), `test_snapshot` (8), `test_service_hours` (2) | none material |
| WS03 orders | `test_state_machine` (9), `test_commands` (11), `test_totals` (6), `test_events` (3), `test_rebuild` (2) | no test asserts the `TRANSITIONS` table is *exhaustively* exercised; a new illegal-transition pair could be added and no test would notice |
| **WS03 floor** | **none** | **`apps/floor/` has zero tests.** `GET /tables`, `GET /sessions/{id}`, `GET /sessions/{id}/bill`, `POST /sessions/{id}/close`, all four `SESSION_*` projections and the whole of `state_chip.py` are untested. The bill — the artefact the guest pays against — has no test of its own. Largest gap in the repository. |
| WS04 realtime | `test_stream` (8), `test_stream_integration` (9) | none material |
| WS05 payments | `test_payments` (18) plus the 935-line `service_script.py` 20-table fixture from WS05b | none material; the service script is the strongest money test in the repo |
| WS07 frontend | `money.test.ts` (6), `modifiers.test.ts` (4) | zero component or interaction tests; `e2e/smoke.spec.ts` exists but CI never runs Playwright, so the WS07 exit criteria are unverified by any automated check |
| WS08 KDS | `urgency.test.ts` (6), `sse.test.ts` (8) — thresholds, server offset and `seq` dedupe all covered as the task requires | `e2e/kds.spec.ts` covers the required "ticket moves across columns; 86 flow" but, again, CI never runs it |
| WS13 infra | none | expected for infra, but the `backup-restore-test.yml` workflow is the only verification and its schedule should be confirmed |

Two further gaps: `apps/reporting/` has no tests (WS06 in flight — but note M1 above is in that code),
and `apps/printing/` is an empty app with only `apps.py` (WS12 in flight).

---

## 7. Uncommitted and extra artifacts

| Artifact | State | Recommendation |
|---|---|---|
| `Claude outputs/` | **Does not exist.** No such directory in the main checkout, in any of the ten worktrees, or in git history. | Nothing to do. |
| `backend/.dockerignore` | Tracked and committed on `develop`. | Nothing to do — already resolved. |
| `README.md` | Clean, unmodified, matches `develop`. | Nothing to do — already resolved. |
| `backend/apps/reporting/queries.py` | Untracked in the main checkout (which is on `ws/06-reporting`). ~385 lines: the four owner queries from `01-product-spec.md` §8 plus the nightly rollup. Legitimate WS06 work in progress. | **Commit it on `ws/06-reporting`, after fixing M1** (`round(money_taken / bills)` at line 190). Do not let it reach `develop` with a float in a money expression. |
| `.claude/` | Present in the main checkout, gitignored (`.gitignore:39`). | Nothing to do. |
| `.qodo/` | Present in the main checkout, **not** in `.gitignore`. Currently invisible to `git status`, presumably via a global excludes file — which means it will appear for anyone without that global config. | Add `.qodo/` to `.gitignore`. |
| `.pytest_cache/` | Present in the main checkout, gitignored (`.gitignore:33`). | Nothing to do. |
| `frontend/mock/openapi.json` | Tracked. A second, hand-maintained schema for the same API. | Delete it and point `npm run mock` at `backend/openapi.json`, as WS07's own task file specifies. See H1. |
| `npm ci` audit | 34 advisories: 25 moderate, 9 high. | Triage the 9 high before the first production deploy; none is a runtime dependency of the ordering path on first inspection, but that needs confirming rather than assuming. |

---

## 8. Prioritised remediation backlog

Ordered by leverage. Each item is scoped to a single agent run.

**R1 — Point `npm run types` and `npm run mock` at `backend/openapi.json`; delete `frontend/mock/openapi.json`.**
Fixes H1 at the root and removes the second source of truth. One line of `package.json`, one file
deleted, then `make types` and commit the regenerated `schema.d.ts`. Do this first: every item below
that touches the frontend is worth less while two generators disagree.
*Owner: WS07. Files: `frontend/package.json`, `frontend/mock/`, `frontend/lib/api/schema.d.ts`.*

**R2 — Add CI on `develop`.**
Change `ci.yml`'s trigger to `push: branches: [main, develop]`. Then run it once and fix whatever it
finds. Until this lands, every "`develop` is green" claim — including this audit's — rests on one
person's laptop. Two lines of YAML.
*Owner: WS13. Files: `.github/workflows/ci.yml`.*

**R3 — Write `docs/06-design-prompts.md`.**
Palette (the CSS variables already in `frontend/app/globals.css` are the de facto tokens — promote
them), type scale, the 56 px / 64 px touch-target rule, guest-light vs staff-dark, no hover-only, no
staff animation except the KDS timer, and the per-screen specs `CLAUDE.md` promises. WS09, WS10 and
WS11 all build UI and all currently have nothing to build against.
*Owner: whoever owns the design language. Files: `docs/06-design-prompts.md`.*

**R4 — Give the command views request and response schemas.**
Add `@extend_schema` (or output serializers) to the 17 POST operations and `TablesView` that spectacular
cannot introspect, until `manage.py spectacular` reports zero errors. Regenerate `openapi.json` and
`schema.d.ts`. This is the prerequisite for R5 and it stops WS09/WS10/WS11 from adding more casts.
*Owner: WS00/core, coordinated with WS03 and WS01. Files: `backend/apps/orders/views.py`,
`backend/apps/accounts/views.py`, `backend/apps/floor/views.py`.*

**R5 — Delete the `as unknown as` casts and the hand-written response types.**
Once R4 lands, replace the nine casts listed in H2 with the generated types and strip the duplicated
interfaces from `frontend/lib/domain.ts`, keeping only the genuinely client-side types (`DraftLine`,
`OrderMode`, the `tableChip` helper).
*Owner: WS07, with WS08 for the two KDS files. Files: `frontend/lib/domain.ts`,
`frontend/app/login/page.tsx`, `frontend/app/guest/[qr_token]/page.tsx`,
`frontend/components/OrderScreen.tsx`, `frontend/components/kds/KdsBoard.tsx`,
`frontend/components/kds/EightySixSheet.tsx`.*

**R6 — Test `apps/floor/`.**
`GET /tables` with and without an open session, `POST /sessions` including the 409 `table_occupied`
path, `GET /sessions/{id}/bill` against snapshot lines and a discount, `POST /sessions/{id}/close`
refusing an unsettled bill, the four `SESSION_*` projections, and every branch of `state_chip.py`. The
bill is the guest-facing money artefact and it is the one thing with no test.
*Owner: WS03. Files: `backend/apps/floor/tests/`.*

**R7 — Fix the float in `reporting/queries.py:190` before `ws/06-reporting` merges.**
`round(money_taken / bills)` → integer division or the `totals.py` helper. Then commit `queries.py`,
which is currently untracked.
*Owner: WS06. Files: `backend/apps/reporting/queries.py`.*

**R8 — Raise the nine sub-56 px staff touch targets.**
The table in M2 lists file and line for each. Ideally paired with R3 so there is a document to cite.
*Owner: WS07, with WS08 for none of them (KDS is already compliant). Files: `frontend/components/DraftPanel.tsx`,
`ModifierSheet.tsx`, `OrderScreen.tsx`, `AuthoriseSheet.tsx`, `MenuBrowser.tsx`, `frontend/app/login/page.tsx`.*

**R9 — Run Playwright in CI.**
Add `npm run test:e2e` against Prism to the frontend job. WS07 and WS08 both have e2e specs whose exit
criteria nothing currently checks.
*Owner: WS13. Files: `.github/workflows/ci.yml`, `frontend/playwright.config.ts`.*

**R10 — Housekeeping.**
Four unrelated one-liners, safe to batch: fix the double-encoded ellipsis in
`frontend/components/OrderScreen.tsx:186,205`; retitle `docs/09-api-contract.md:1` from "08" to "09";
add `.qodo/` to `.gitignore`; document `GET /auth/owner/me` and `GET /guest/sessions/{session_id}` in
`docs/09-api-contract.md` §3.

**R11 — Consolidate the session-projection helpers and triage the npm advisories.**
Move `_refresh_session_bill` and `_refresh_session_paid` beside the `TableSession` aggregate (or into a
shared `floor/projections.py`) so one file explains how a session's numbers are derived; fold
`current_shift_for` into `open_shift_for`. Separately, triage the 9 high npm advisories. Lowest
priority — nothing here is wrong today, it is only harder to change than it needs to be.
