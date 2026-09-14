# WS09 — Cashier

**Goal:** payment recording in two taps, change shown large, split and partial payments as the normal
case, and the shift open/close that makes the variance number real.

**Depends on:** WS05, WS07. **Blocks:** nothing.

## Owns

`frontend/app/cashier/`.

## Build

1. **Shift gate**: no open shift → "Open shift" screen with opening float (numeric pad, pesewas
   under the hood, `GH₵` display). Close shift: count sheet (declared cash), then Z-report view showing
   expected / declared / variance with the variance in red or green and the size of a headline.
2. **Open bills** list from `/bills/open` with state chips `sent / cooking / food ready / ready to pay /
   part paid`, table number, age, balance. Live via the stream.
3. **Bill view**: lines from `/sessions/{id}/bill` (snapshots, modifiers, discounts), total, payments so
   far, balance. Actions: pay, discount (authorisation sheet), void order (authorisation sheet if past
   submitted), reopen (authorisation), reprint receipt (sends a `PRINT_RECEIPT` request — WS12 defines it).
4. **Pay sheet**: method buttons (Cash, MTN MoMo, Telecel Cash, AirtelTigo, Card, Bank); amount defaults to
   the balance and is editable for splits; cash shows quick-tender buttons (exact, 50, 100, 200) and the
   change **very large**; MoMo shows a forgiving reference field (auto-uppercase, spaces ignored). Submit →
   `POST /sessions/{id}/payments` with `Idempotency-Key`; on settle, show "Paid in full" and offer receipt.
5. **Drawer**: no-sale, paid out, paid in — each behind the authorisation sheet with reason codes.
6. Guard rails in the UI mirror the server: cannot pay a bill with unserved orders (button disabled with
   the reason), cannot overpay (amount capped at balance, cash tendered may exceed).

## Tests required

- Vitest: change calculation with integers; amount capping; reference normalisation preview.
- Playwright against the mock: open shift → pay a bill in two methods → close shift with a variance.

## Exit criteria

A cashier settles a four-way split with three MoMo references and one cash payment without touching
the keyboard for anything but the references.
