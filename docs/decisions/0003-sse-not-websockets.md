# ADR-0003 — Server-Sent Events, not WebSockets

**Status:** Accepted · 2026-09-14

## Context

The kitchen display, cashier and owner dashboard must update the moment something happens. The
reflex choice is WebSockets.

## Decision

**Server-Sent Events** over Redis pub/sub, with automatic fallback to 3-second polling after two
consecutive stream failures.

## Rationale

Look at the actual traffic shape. **Everything the server sends is a broadcast. Everything the client
sends is a command.**

Commands want HTTP semantics: status codes, retries, `Idempotency-Key`, standard auth headers,
ordinary request logging. Broadcasts want one persistent downstream channel. That is precisely SSE.

| | SSE | WebSockets | Polling |
|---|---|---|---|
| Reconnection | **Automatic in `EventSource`, with `Last-Event-ID` replay** | Hand-written every time | n/a |
| Auth | Standard HTTP headers and cookies | Custom handshake | Standard |
| Proxies, captive portals, mobile networks | Plain HTTP, passes through | Frequently blocked | Best |
| Ops | One async view | ASGI + channel layer + scaling story | Lowest |
| Battery / data | Low | Low | Poor |

`Last-Event-ID` is decisive. A kitchen tablet that loses WiFi for 90 seconds reconnects and
**automatically receives the events it missed, in order**, replayed from `order_events.seq`. With
WebSockets that catch-up logic is yours to write, and it is easy to get subtly wrong in a way that
loses a ticket — which in this product means a guest waits an hour for food.

Nothing in the system needs client→server push over a socket. The bidirectionality of WebSockets is
capability we would pay for and not use.

## Consequences

- One connection per device held open. Trivial at one restaurant; sizing matters only at scale.
- **The SSE endpoint must not run on serverless.** Vercel/Netlify function timeouts kill long-lived
  connections. Frontend on Vercel is fine; the stream lives on the VPS.
- Django async view + `redis.asyncio`. Keep the ORM work sync and outside the stream loop.
- Polling fallback must exist and be tested, not assumed.

## Revisit when

Fan-out becomes a maintenance burden, or a genuine client→server streaming need appears. The
replacement is [Centrifugo](https://centrifugal.dev) — a single Go binary speaking both SSE and
WebSocket with JWT channel auth and history recovery — not a hand-rolled WebSocket layer.
