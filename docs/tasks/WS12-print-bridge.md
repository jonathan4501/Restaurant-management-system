# WS12 — Print bridge and receipts

**Goal:** paper. Kitchen backup tickets when the display fails, and a guest receipt at settlement.
Browsers cannot talk ESC/POS; the Raspberry Pi can.

**Depends on:** WS04. **Blocks:** nothing.

## Owns

`bridge/`, `backend/apps/printing/`.

## Build

1. **Backend** `apps/printing`: pure functions `render_kitchen_ticket(envelope) -> bytes` and
   `render_receipt(bill) -> bytes` using `python-escpos` (`Dummy` printer to produce bytes). Ticket: order
   number huge, table, time, lines with modifiers indented, station header, cut. Receipt: RENZY header,
   table, lines with snapshots, discounts, **total**, payments by method, change, "Thank you". The receipt
   is titled **"Sales record"** — never "Invoice", never "VAT" (ADR-0005). No tax lines exist to print.
   A command `POST /print/receipt {session_id}` (CASHIER+) emits `RECEIPT_REQUESTED` (add to vocabulary
   under `SESSION`) so reprints are logged — a reprinted receipt reused to legitimise an unrecorded sale is
   fraud pattern 5 in `01-product-spec.md`.
2. **Bridge** `bridge/renzy_bridge/`: Python 3.12 daemon; config in `/etc/renzy-bridge.toml` (API URL,
   device token, printer IPs per role); SSE client (`httpx` streaming) with `Last-Event-ID` persisted to
   disk after every processed event; prints `ORDER_SUBMITTED` to the kitchen printer (per station if
   configured), `SESSION_SETTLED` and `RECEIPT_REQUESTED` to the front printer; local SQLite queue so a
   printer that is off gets the ticket when it returns; `systemd` unit with restart; healthcheck log line
   every minute; `bridge/README.md` with the Pi setup in ten steps.
3. Bridge enrols as a device with `allowed_roles=['PRINTER']` — add that role value to `devices.allowed_roles`
   validation (not to `staff.role`). The stream filter treats `PRINTER` like KITCHEN + SESSION events.

## Tests required

- Byte-level snapshot tests for ticket and receipt renders (golden files).
- Bridge: replay-from-disk after restart; printer unreachable → queued → printed when reachable
  (fake TCP server in the test).

## Exit criteria

Pull the kitchen display's power; the ticket for the next order comes out of the kitchen printer within
five seconds of "Send".
