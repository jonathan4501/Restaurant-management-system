# WS08 — Kitchen display

**Goal:** the timer. A late ticket must be impossible to miss from across the kitchen.

**Depends on:** WS04, WS07. **Blocks:** nothing.

## Owns

`frontend/app/kds/`, `frontend/lib/realtime/` (the EventSource hook, shared with cashier and owner).

## Build

1. `useEventStream()` hook implementing `frontend/lib/realtime/README.md` from WS04: EventSource with
   auth headers (use `fetch` + `ReadableStream` since `EventSource` cannot set headers; keep the
   `Last-Event-ID` semantics), dedupe by `seq`, fallback to polling after two failures, `RESYNC` refetch,
   `AUTH_EXPIRED` → login. Invalidate TanStack queries by aggregate.
2. Three columns **New / Preparing / Ready**, full-screen, landscape, dark theme, no chrome.
3. Ticket card: order number, table, age `mm:ss` from `submitted_at` (New) or `acknowledged_at`
   (Preparing) using **server time offset** (compute `serverNow − clientNow` from the response `Date`
   header; never trust the device clock). Amber at 10:00, red at 15:00 with a pulsing border.
4. Lines: item name, quantity, **modifiers in a distinct colour**, notes, station tag. `?station=`
   filter from a top toggle (ALL / KITCHEN / GRILL / BAR) persisted in localStorage.
5. Actions: tap card → ack (New → Preparing); per-line tap → item ready; "All ready" → order ready;
   Ready column → "Served" (waiter or kitchen). Every action sends a command with `Idempotency-Key`;
   optimistic move with a pending outline until the stream confirms.
6. **86 button**: opens the item list, one tap marks finished, confirms with a big toast; restore in the
   same list.
7. Sound: a short chime on `ORDER_SUBMITTED` (user-enabled once per session; browsers block autoplay).
8. Backup: if the stream and polling both fail for 60 s, a full-width red banner "OFFLINE — check the
   printer for tickets".

## Tests required

- Vitest: urgency thresholds, server-offset timer, dedupe by `seq`.
- Playwright against the mock: ticket moves across columns; 86 flow.

## Exit criteria

On a 21-inch screen from four metres away, a red ticket is unmistakable, and the grill cook can read
only grill lines.
