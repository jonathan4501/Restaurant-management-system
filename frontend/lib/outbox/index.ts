/**
 * The outbox as the rest of the app sees it.
 *
 * `lib/api/client.ts` hands us its `fetch`, so every POST it makes is written to IndexedDB before
 * it is attempted, online or not. Nothing else in the app calls the outbox directly: a screen
 * keeps calling `api.POST(...)` and gets a normal-looking result back.
 */

import { v7 as uuidv7 } from "uuid";

import { Outbox } from "./outbox";
import { classifyCommand } from "./policy";
import { blockedResponse } from "./responses";
import type { OutboxCommand, OutboxEntry } from "./types";

export { Outbox, CONFLICT_ATTEMPTS, type Scheduler, type Transport } from "./outbox";
export { backoffMs, BASE_BACKOFF_MS, MAX_BACKOFF_MS } from "./backoff";
export { classifyCommand, type CommandPolicy, type CommandRule } from "./policy";
export {
  blockedResponse,
  isQueued,
  outboxState,
  queuedResponse,
  OUTBOX_HEADER,
  QUEUED_STATUS,
} from "./responses";
export type { OutboxCommand, OutboxEntry, OutboxSnapshot, OutboxStatus } from "./types";

const IDEMPOTENCY = "idempotency-key";
const CLIENT_TIME = "x-client-time";

export interface OutboxFetchConfig {
  baseUrl: string;
}

/**
 * `navigator.onLine` is a hint, not a promise. It is right about *offline* often enough to skip a
 * doomed request, and wrong about *online* whenever the router is up but the WAN is not — which is
 * the Accra case exactly, and why a failed attempt backs off rather than trusting this.
 */
export function isOnline(): boolean {
  if (typeof navigator === "undefined") return true;
  return navigator.onLine !== false;
}

let config: OutboxFetchConfig = { baseUrl: "" };

function transport(entry: OutboxEntry): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 20_000);
  return fetch(`${config.baseUrl}${entry.path}`, {
    method: entry.method,
    headers: {
      ...entry.headers,
      // Re-stated rather than merely inherited: these two are the whole reason a replay is safe.
      [IDEMPOTENCY]: entry.idempotencyKey,
      [CLIENT_TIME]: entry.clientTime,
    },
    body: entry.body === null || entry.body === undefined ? undefined : JSON.stringify(entry.body),
    cache: "no-store",
    signal: ctrl.signal,
  }).finally(() => clearTimeout(timer));
}

export const outbox = new Outbox({ transport, isOnline });

/** Hop-by-hop and length headers are the fetch layer's business, not ours to replay. */
const SKIP_HEADERS = new Set(["content-length", "host", "connection"]);

/** Lower-cased throughout so replaying cannot produce two spellings of the same header. */
function captureHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    const name = key.toLowerCase();
    if (!SKIP_HEADERS.has(name)) headers[name] = value;
  });
  return headers;
}

async function readBody(request: Request): Promise<unknown> {
  const text = await request.clone().text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/** The entity id the command creates, when it carries one — that is what an optimistic UI keys on. */
function entityId(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "id" in body) {
    const id = (body as { id?: unknown }).id;
    if (typeof id === "string" && id.length > 0) return id;
  }
  return fallback;
}

/**
 * Configure the outbox and return the `fetch` for `createClient`. Takes the base URL as an
 * argument rather than importing it, so there is no cycle back into the API client.
 */
export function createOutboxFetch(next: OutboxFetchConfig): (request: Request) => Promise<Response> {
  config = next;
  return outboxFetch;
}

export async function outboxFetch(request: Request): Promise<Response> {
  if (request.method !== "POST") return fetch(request);

  const url = new URL(request.url);
  const rule = classifyCommand(url.pathname);
  if (rule.policy === "online-only") {
    if (!isOnline()) return blockedResponse(rule);
    return fetch(request);
  }

  const headers = captureHeaders(request);
  const body = await readBody(request);
  const idempotencyKey = headers[IDEMPOTENCY] || uuidv7();
  headers[IDEMPOTENCY] = idempotencyKey;
  const clientTime = headers[CLIENT_TIME] || new Date().toISOString();
  headers[CLIENT_TIME] = clientTime;

  const command: OutboxCommand = {
    id: entityId(body, idempotencyKey),
    path: `${url.pathname}${url.search}`,
    body,
    idempotencyKey,
    clientTime,
    headers,
  };
  return outbox.submit(command);
}

/**
 * Start draining and keep draining: on reconnect, on the tab coming back to the front (a tablet
 * that was asleep in an apron pocket), and once at startup for whatever the last shift left behind.
 */
export function startOutbox(): () => void {
  void outbox.resume();
  if (typeof window === "undefined") return () => {};

  const wake = () => void outbox.resume();
  const onVisible = () => {
    if (document.visibilityState === "visible") wake();
  };

  window.addEventListener("online", wake);
  window.addEventListener("focus", wake);
  document.addEventListener("visibilitychange", onVisible);
  return () => {
    window.removeEventListener("online", wake);
    window.removeEventListener("focus", wake);
    document.removeEventListener("visibilitychange", onVisible);
  };
}
