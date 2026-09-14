/**
 * The offline outbox (ADR-0002). WS11 implements the store and the drain; these types are fixed now
 * so WS07's client code can be written against them.
 *
 * Every command is written here first, then sent. Replay after reconnect is safe because the
 * Idempotency-Key travels with the entry and the server returns the original response on repeat.
 */

export type OutboxStatus = "queued" | "sending" | "failed";

export interface OutboxEntry {
  /** UUIDv7, also the entity id when the command creates one. */
  id: string;
  /** Monotonic per device; drain order. */
  seq: number;
  method: "POST";
  /** Path relative to the API base, e.g. "/api/v1/orders/<id>/submit". */
  path: string;
  body: unknown;
  idempotencyKey: string;
  /** ISO 8601, the device clock at enqueue time → X-Client-Time. */
  clientTime: string;
  status: OutboxStatus;
  attempts: number;
  lastError: string | null;
  /** HTTP status of the terminal failure (4xx other than 409/429), if any. */
  failedStatus: number | null;
}

export interface OutboxSnapshot {
  queued: number;
  failed: number;
  online: boolean;
}
