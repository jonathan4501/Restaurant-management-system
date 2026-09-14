# WS07 — Frontend shell and ordering (waiter / guest / qr)

**Goal:** the one PWA with role-scoped views, the PIN login, and the ordering screen in its three modes.
Learnable in ten minutes with no manual: large targets, no nested menus.

**Depends on:** WS00 (shell, `openapi.json`, mock), WS02, WS03 for real data. Start against the mock.
**Blocks:** WS08, WS09, WS10, WS11.

## Owns

`frontend/` except `app/kds/`, `app/cashier/`, `app/owner/`, `lib/outbox/`, `sw/`.

## Build

1. **Mock**: `npm run mock` runs Prism on `../backend/openapi.json` with example responses; every screen must
   work against it so UI work never waits on the backend.
2. **App shell**: `app/layout.tsx` with device context (token, allowed roles), staff context (JWT, role),
   connectivity badge (online / offline / pending N), TanStack Query provider, Zustand stores
   (`useDevice`, `useStaff`, `useDraft`). Installable PWA manifest (icons, standalone, landscape for KDS).
3. **Login**: device enrolment screen (code entry, once) → PIN pad (staff avatars from `/devices/me`, 4–6
   digits, big keys, error and lockout countdown from 423). Role routes: WAITER → `/order`, KITCHEN → `/kds`,
   CASHIER → `/cashier`, MANAGER → chooser, OWNER → `/owner`.
4. **Ordering** `app/order/`: table grid from `/tables` with state chips → session → draft. Category
   tabs, item grid with images and `is_available` greyed (86'd items are not tappable and vanish on the
   stream event), modifier sheet (`ONE` = radio, `MANY` = checkbox, required groups enforced, paid extras
   show `+GH₵ x.xx`), quantity, notes, draft panel with line totals, "Send to kitchen" which submits with a
   fresh `Idempotency-Key` and shows the pending state honestly until the 2xx arrives.
5. **Modes** via `useOrderMode()`: `waiter` (default, full), `guest` (handed tablet: locked to one session,
   no table grid, no other bills, exit requires staff PIN), `qr` (own phone via `/guest/sessions/{qr_token}`,
   same components, polling own order status every 5 s). Guest and qr use the guest token and the
   `/guest` client. A Twi toggle for guest-facing strings (`lib/i18n`, two files, English fallback).
6. **Manager authorisation sheet** (`components/AuthoriseSheet`): PIN + reason code list per purpose;
   returns the token to the calling command; reused by cashier and KDS.
7. **Money**: `formatPesewas` only. Playwright smoke: login → open table → add item with modifier → send.

## Tests required

- Vitest: draft store line totals (integers), modifier rules, mode gating (guest cannot see `/tables`).
- Playwright against the mock: the smoke above, plus 86'd item not addable.

## Exit criteria

A waiter with no training opens a table, orders jollof with extra plantain and two Club beers, and
sends it, in under a minute, on a 10-inch Android tablet in Chrome.
