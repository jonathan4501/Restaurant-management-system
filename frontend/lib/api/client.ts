/**
 * The typed API client. Types come from lib/api/schema.d.ts, generated from backend/openapi.json
 * (`npm run types`). Never hand-write request or response types.
 *
 * Every request carries the device token and the session token. Every POST carries a fresh
 * Idempotency-Key (UUIDv7) and X-Client-Time. WS11 routes POSTs through the IndexedDB outbox;
 * until then this client talks to the network directly.
 */

import createClient, { type Middleware } from "openapi-fetch";
import { v7 as uuidv7 } from "uuid";

import { tokens } from "@/lib/auth/tokens";

import type { paths } from "./schema";

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const IDEMPOTENCY_HEADER = "Idempotency-Key";

/** A problem+json body (RFC 9457) as the backend sends it. `code` is what UI switches on. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  code: string;
  detail: string;
  errors: Record<string, unknown>;
  retry_after_seconds?: number;
}

export function isProblem(value: unknown): value is Problem {
  return typeof value === "object" && value !== null && "code" in value && "status" in value;
}

const headers: Middleware = {
  async onRequest({ request }) {
    const device = tokens.device();
    const session = tokens.session();
    if (device) request.headers.set("X-Device-Token", device);
    if (session) request.headers.set("Authorization", `Bearer ${session}`);
    if (request.method === "POST") {
      if (!request.headers.has(IDEMPOTENCY_HEADER)) request.headers.set(IDEMPOTENCY_HEADER, uuidv7());
      request.headers.set("X-Client-Time", new Date().toISOString());
    }
    return request;
  },
};

export const api = createClient<paths>({ baseUrl: API_BASE_URL });
api.use(headers);

/** Generate the key up front when a command will be queued or retried (outbox, double-tap guard). */
export function newIdempotencyKey(): string {
  return uuidv7();
}
