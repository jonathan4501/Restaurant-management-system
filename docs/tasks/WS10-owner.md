# WS10 — Owner back office

**Goal:** the owner opens the dashboard and the first thing on screen is where money can leak.

**Depends on:** WS06, WS07. **Blocks:** nothing.

## Owns

`frontend/app/owner/`.

## Build

1. Owner login: email + password, then TOTP; session cookie; works on a phone.
2. Landing = **variance panel**, in this order: cash variance by shift and cashier (last 7 days, red
   negatives), voids after cooking (value, reason, who, who authorised), discounts and comps by staff
   member, reopened bills, order-number gaps. Each row links to the event log filtered to it.
3. **Today**: "Money taken" (that label, verbatim), covers, average bill, open bills now. Live via the
   stream (OWNER role sees everything).
4. **Patterns**: money taken by hour (bar), payment mix (donut), best sellers by value (table),
   order-to-ready per station (table). Charts via a small dependency (Recharts); load the `dataviz`
   guidance before styling.
5. **Event log**: infinite scroll by cursor, filters (staff, type, aggregate, date), flagged rows
   visually distinct, each row expandable to the payload.
6. Menu and staff administration link out to Django admin (same origin, owner session).
7. Every gross figure is labelled "Money taken" or "Total collected". A test greps the owner bundle for
   "Revenue" and "Profit" and fails if found.

## Tests required

- Vitest: label guard; variance colouring; cursor merging.
- Playwright against the mock: login with TOTP → variance panel renders → log filter by staff.

## Exit criteria

The owner, on a phone over mobile data, sees last night's variance within five seconds of opening the app.
