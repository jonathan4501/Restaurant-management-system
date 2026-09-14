# 02 — Architecture

Decisions with their reasoning. Each major choice also has a short ADR in `decisions/`.

---

## 1. The governing constraint

The developer is in **Lomé, Togo**. The restaurant is in **Shiashi, Accra** — about 190 km away,
across a border. Nobody is going to drive there to reboot a box during Friday dinner service.

That single fact outranks technical elegance. Everything must be **remotely deployable, remotely
debuggable, and remotely recoverable**. Any design that puts a critical, stateful, hand-maintained
machine inside the restaurant is a design that eventually puts a developer on a bus.

---

## 2. Where truth lives during service

| Option                                   | Shape                                                                                                                                     | Verdict                                                                             |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Cloud-only                               | Devices hit a cloud API, no local state                                                                                                   | **No.** Dies with the internet. Accra outages are routine.                          |
| On-premise-first                         | A server in the restaurant is truth, replicates to cloud                                                                                  | Most robust during outages, but see §1. Hardware failure becomes a border crossing. |
| **Cloud-primary + durable client queue** | Cloud is truth. Each device is a PWA with an IndexedDB outbox. Writes are client-ID'd and idempotent, queue offline, replay on reconnect. | ✅ **Chosen.**                                                                      |

### Why the client queue is safe here

Because **orders are append-only** (§4), independent offline writes have essentially no conflict
surface. Two waiters offline, both adding items, produce a union — which is the correct answer. There
are no CRDTs, no vector clocks, no merge logic.

The only genuinely conflicting state is **item availability (86)** and **payment status**. Both stay
server-authoritative; clients render them as pending until the server confirms.

### Migrating later, if outage data justifies it

Every device speaks one API contract. Moving to on-premise means pointing them at a local node that
speaks the same contract and replicates upstream. A deployment change, not a rewrite.
**Measure three months of real outages before spending money on this.**

---

## 3. System shape

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Waiter /     │  │ Kitchen      │  │ Cashier      │  │ Owner        │
│ Guest        │  │ Display      │  │ Terminal     │  │ Back office  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                 │
       │   ONE Next.js PWA — role-scoped views, service worker, IndexedDB outbox
       └────────┬────────┴────────┬────────┴────────┬────────┘
                │                 │                 │
        POST commands       SSE event stream   GET projections
        (idempotent)        (server → client)
                ▼                 ▼                 ▼
       ┌────────────────────────────────────────────────┐
       │  Django + DRF (ASGI)            VPS, Docker    │
       │   command handlers → validate, append, project │
       │   SSE fan-out via Redis pub/sub                │
       │   Celery: reports, backups, nightly summary    │
       └───────────────┬────────────────────────────────┘
                       ▼
              ┌─────────────────┐            ┌────────────────────┐
              │ PostgreSQL      │            │ Print bridge (Pi)  │
              │ events +        │◄──SSE──────│ ESC/POS → TCP:9100 │
              │ projections     │            │ kitchen + receipt  │
              └─────────────────┘            └────────────────────┘
```

---

## 4. Event sourcing

`order_events` **is the source of truth. Order state is a fold over events, materialised into
projection tables for fast reads.**

Why:

- The client's requirement — _"track every action done by customers, kitchen and cashier"_ — is
  satisfied **by construction**. You cannot forget to log something, because logging _is_ the write.
- Voids, comps and overrides are events, not deletions. Nothing is destroyed, so the fraud reporting
  is trustworthy rather than merely present.
- Offline conflict resolution is trivial: append is commutative across independent actors.
- "What exactly happened to table 7 last Friday" is a query, not an investigation.

Cost, honestly: roughly 20–30% more backend code, and reports must read projections rather than
folding the log at query time. For an anti-theft product this repays itself at the first dispute.

Rules:

- `UPDATE` and `DELETE` are **revoked at the database level** on `order_events`.
- Every event carries `actor_id`, `actor_role`, `device_id`, and `authorised_by` when an override
  was involved.
- Projections are rebuildable from the log. Never let a projection become the only copy of a fact.

---

## 5. Realtime: SSE, not WebSockets

Look at the actual traffic. **Everything the server sends is a broadcast. Everything the client sends
is a command.** Commands want HTTP semantics — status codes, retries, idempotency keys, ordinary auth
and logging. Broadcasts want a persistent one-way channel. That is exactly Server-Sent Events.

|                           | SSE                                            | WebSockets                        | Polling               |
| ------------------------- | ---------------------------------------------- | --------------------------------- | --------------------- |
| Reconnection              | **Automatic, with** `Last-Event-ID` **replay** | You write it yourself, every time | n/a                   |
| Auth                      | Standard HTTP headers/cookies                  | Custom handshake                  | Standard              |
| Proxies / captive portals | Plain HTTP, passes through                     | Often blocked                     | Best                  |
| Ops complexity            | Low                                            | ASGI + channel layer + scaling    | Lowest                |
| Fit                       | ✅                                             | Over-engineered here              | Laggy, drains battery |

`Last-Event-ID` is the decisive feature: a kitchen tablet that loses WiFi for 90 seconds reconnects
and **automatically receives the events it missed, in order**. With WebSockets you build that
yourself and get it subtly wrong.

**Implementation:** Django async view → `redis.asyncio` subscription → SSE stream. Replay from
`order_events` by sequence. Client falls back to 3-second polling after two consecutive stream
failures.

**Trap:** do not host the SSE endpoint on Vercel/Netlify serverless. Execution timeouts kill
long-lived connections. Frontend on Vercel is fine; the stream lives on the VPS.

**Escape hatch:** if fan-out becomes a maintenance burden, [Centrifugo](https://centrifugal.dev) is a
single Go binary that speaks SSE and WebSocket with JWT channel auth and history recovery. Adopt it
when there is a reason, not before.

---

## 6. Offline

**Client**

1. Service worker caches app shell, menu and modifiers. The app opens and works with no network.
2. Every command goes to an **IndexedDB outbox** with a client-generated UUIDv7 and a monotonic
   client sequence number.
3. The outbox drains FIFO with exponential backoff, each request carrying `Idempotency-Key`.
4. The UI shows optimistic state with a visible **"pending sync"** marker.
   **Never lie about this.** A waiter who believes the kitchen received an order it did not receive
   will lose you the contract faster than any bug.
5. On reconnect: drain the outbox, then reconnect SSE with `Last-Event-ID`, then reconcile.

**Server**

1. `Idempotency-Key` is unique-indexed; replays return the original response.
2. The server assigns authoritative sequence and timestamps. Client time is stored for audit only.
3. Append-only means a late event is simply appended with its true client time. No merge logic.

---

## 7. Authentication and authorisation

- **Staff:** 4–6 digit PIN, hashed with **argon2id**. Five attempts, then a 15-minute device lockout.
  Failed attempts are logged against the device.
- **Owner / Manager:** email + password + TOTP.
- **Devices are enrolled**, each with a revocable token and an allowed-role list. An un-enrolled
  device cannot post an order. Revoke from the back office when a tablet walks.
- **Guest mode is sandboxed hard.** A short-lived token scoped to one table session, permitted to do
  exactly two things: read the menu, and add items to its own draft. It cannot see other tables,
  other bills, staff functions, or any total but its own. Treat it as hostile input.

Manager PIN + mandatory reason code required for: void after kitchen acknowledgement, discount, comp,
price override, reopening a closed bill, drawer no-sale, menu price edits during service.
Each writes an event naming **both actor and authoriser** — that two-name requirement is what makes
collusion visible.

---

## 8. Printing

Browsers cannot send raw ESC/POS to a network printer. This surprises people late; plan for it now.

A **Raspberry Pi print bridge** in the restaurant runs a small daemon that subscribes to the SSE
stream and pushes ESC/POS over TCP:9100.

- Kitchen printer — backup tickets when the display fails. Cheap insurance; kitchens trust paper.
- Front printer — guest receipt.
- The same Pi becomes the local node if the project ever moves to on-premise-first. It pays for itself twice.

Printers: Epson TM-T82 / TM-T20 (reliable, well-documented ESC/POS) or Xprinter XP-N160II (cheaper).
**Ethernet or WiFi models, not USB** — USB chains you to one specific computer.

---

## 9. Hosting

| Component       | Choice                                                    | Note                                                        |
| --------------- | --------------------------------------------------------- | ----------------------------------------------------------- |
| API + Redis     | Hetzner or DigitalOcean, Amsterdam/London, Docker Compose | ~120–150 ms to Accra, irrelevant for push                   |
| Frontend        | Vercel                                                    | Keep SSE off serverless                                     |
| Database        | **Managed** PostgreSQL                                    | Losing a restaurant's sales data once ends the relationship |
| Files           | Cloudflare R2 or Backblaze B2                             | No egress fees                                              |
| CDN / DNS / TLS | Cloudflare                                                | Free                                                        |
| Errors          | Sentry                                                    | You are not in the room when it breaks                      |
| Uptime          | UptimeRobot or Better Stack                               | Find out before the owner calls                             |

Deployment is Docker Compose plus GitHub Actions over SSH. **No Kubernetes.** One restaurant does not
need an orchestrator, and you would be maintaining it at 22:00 on a Friday.

If self-hosting Postgres anyway: `pg_dump` plus WAL archiving to object storage, **and a restore test
every month**. An untested backup is not a backup.

---

## 10. Why Django

- Fastest path to shipping for this team, and ship speed is the dominant risk on a first paid build.
- **Django admin is a free back office** on day one: menu CRUD, images, categories, staff,
  permissions, event-log browsing. That is two to three weeks not spent.
- Mature migrations and transaction semantics (`atomic`, `select_for_update`). This handles money.
- Celery already in the toolkit.

The honest counter-argument: a single TypeScript codebase gives one language, one deploy and
end-to-end types. For a funded team building multi-tenant SaaS, that is arguably better. For one
restaurant and one developer, Django's batteries win. Mitigate type drift with
`drf-spectacular` → OpenAPI → `openapi-typescript` in CI.
