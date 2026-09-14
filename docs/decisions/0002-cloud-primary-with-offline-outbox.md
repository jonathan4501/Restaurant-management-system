# ADR-0002 — Cloud-primary with a durable client outbox

**Status:** Accepted · 2026-09-14

## Context

Accra has routine power cuts and unreliable fixed broadband. The restaurant must keep taking orders
and serving food with no internet.

The developer is in **Lomé, Togo — about 190 km from Shiashi, across an international border.**

## Options

| | Shape | Verdict |
|---|---|---|
| Cloud-only | Devices hit a cloud API, no local state | Rejected. Dies with the internet. |
| On-premise-first | A server in the restaurant is truth, replicates to cloud | Technically the most robust during outages. |
| **Cloud-primary + client outbox** | Cloud is truth; each device is a PWA with an IndexedDB outbox, idempotent client-ID'd writes | **Accepted.** |

## Decision

Cloud-primary. Every device queues writes locally and replays them on reconnect.

## Rationale

On-premise-first is better *in a vacuum*. It loses on operations:

- A solo developer 190 km away cannot treat hardware failure as a support ticket. Every corrupted SD
  card, failed PSU or unplugged box becomes a border crossing.
- One deploy, remote updates, remote debugging, no site visits.
- The owner dashboard is free — it is already cloud-side.
- A **dual-SIM 4G failover router (~GH¢1,200) costs less than the mini-PC** and removes most outages
  at the source rather than working around them.
- Because ADR-0001 makes orders append-only, offline writes from several devices have no conflict
  surface. That property is what makes this option safe rather than merely convenient.

The only genuinely conflicting state is item availability (86) and payment status. Both remain
server-authoritative; clients render them as pending until confirmed.

## Consequences

- Client-side complexity: service worker, IndexedDB outbox, optimistic UI with an honest
  **"pending sync"** indicator. Never show an order as delivered to the kitchen when it is still queued.
- Every write endpoint must be idempotent (`Idempotency-Key`, unique-indexed).
- Long outages degrade the owner's live view, not the restaurant's ability to trade.

## Revisit when

Three months of real outage data exist. If outages regularly exceed an hour, add a local node —
it speaks the same API contract, so it is a deployment change, not a rewrite. **Measure first.**
