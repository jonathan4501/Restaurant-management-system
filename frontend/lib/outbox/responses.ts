/**
 * The two answers the outbox gives when the network did not.
 *
 * Both are real `Response` objects so `openapi-fetch` parses them exactly as it parses the server:
 * a 202 lands in `data`, the problem document lands in `error`. No call site needs to know the
 * outbox exists — but any call site that wants to can read the status and tell the truth about it.
 */

import type { CommandRule } from "./policy";
import type { OutboxEntry } from "./types";

/** Present on every response the outbox invented rather than received. */
export const OUTBOX_HEADER = "X-Renzy-Outbox";

/** 202: written to this device's queue, not yet accepted by the server. Never treat as done. */
export const QUEUED_STATUS = 202;

export interface QueuedBody {
  /** The client-generated entity id, so an optimistic screen has something to key on. */
  id: string;
  queued: true;
  idempotency_key: string;
  client_created_at: string;
}

export function queuedResponse(entry: OutboxEntry): Response {
  const body: QueuedBody = {
    id: entry.id,
    queued: true,
    idempotency_key: entry.idempotencyKey,
    client_created_at: entry.clientTime,
  };
  return new Response(JSON.stringify(body), {
    status: QUEUED_STATUS,
    headers: {
      "Content-Type": "application/json",
      [OUTBOX_HEADER]: "queued",
    },
  });
}

/**
 * 503 with an RFC 9457 problem document, shaped exactly like the backend's so
 * `isProblem` / `problemMessage` pick it up and the existing error lines render it unchanged.
 */
export function blockedResponse(rule: CommandRule): Response {
  const body = {
    type: "about:blank",
    title: "Offline",
    status: 503,
    code: rule.code,
    detail: rule.reason,
    errors: {},
  };
  return new Response(JSON.stringify(body), {
    status: 503,
    headers: {
      "Content-Type": "application/problem+json",
      [OUTBOX_HEADER]: "blocked",
    },
  });
}

/** `"queued"`, `"blocked"`, or `null` when this came from the server. */
export function outboxState(response: Response): "queued" | "blocked" | null {
  const value = response.headers.get(OUTBOX_HEADER);
  return value === "queued" || value === "blocked" ? value : null;
}

/** True when the command is sitting in the queue rather than accepted by the kitchen. */
export function isQueued(response: Response): boolean {
  return outboxState(response) === "queued";
}
