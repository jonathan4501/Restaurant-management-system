# Architecture decision records

Why things are the way they are. Read the relevant record before changing a decision — each one lists
what was rejected and the condition under which it should be revisited.

| # | Decision | Status |
|---|---|---|
| [0001](0001-event-sourced-order-log.md) | Orders are an append-only event log | Accepted |
| [0002](0002-cloud-primary-with-offline-outbox.md) | Cloud-primary with a durable client outbox | Accepted |
| [0003](0003-sse-not-websockets.md) | Server-Sent Events, not WebSockets | Accepted |
| [0004](0004-pwa-not-native.md) | One PWA, not native apps | Accepted |
| [0005](0005-no-tax-engine.md) | No tax engine — the system records what was charged | Accepted |
| [0006](0006-record-only-payments.md) | Payments are recorded, not processed | Accepted |
| [0007](0007-single-event-stream.md) | One append-only stream for every action; per-restaurant gapless `seq` | Accepted |
| [0008](0008-bill-is-the-table-session.md) | The bill is the table session; payments settle the session | Accepted |

## Writing a new one

Copy the shape of an existing record: **Context → Decision → Rationale → Consequences → Revisit when.**
State what was rejected and why; a record that only argues for the winner is not a decision record,
it is advocacy.

Number sequentially. Never edit an accepted record to reflect a change of mind — write a new one and
mark the old `Superseded by NNNN`.
