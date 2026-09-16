/**
 * SSE parsing and the rules from lib/realtime/README.md, kept free of React so they can be tested
 * on their own. EventSource cannot send the device and staff headers, so the stream is read from a
 * fetch body; this module turns that byte stream into envelopes.
 */

import type { AggregateType, EventEnvelope } from "@/lib/domain";

export interface SseMessage {
  id: number | null;
  event: string;
  data: string;
}

/** Feed it chunks, get whole messages back. Keeps the half-message tail between calls. */
export class SseParser {
  private buffer = "";

  push(chunk: string): SseMessage[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const messages: SseMessage[] = [];
    let index = this.buffer.indexOf("\n\n");
    while (index !== -1) {
      const block = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      const message = parseBlock(block);
      if (message) messages.push(message);
      index = this.buffer.indexOf("\n\n");
    }
    return messages;
  }
}

function parseBlock(block: string): SseMessage | null {
  let id: number | null = null;
  let event = "message";
  const dataLines: string[] = [];
  for (const rawLine of block.split("\n")) {
    const line = rawLine.replace(/\r$/, "");
    if (line === "" || line.startsWith(":")) continue; // keepalive
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
    if (field === "id") {
      const parsed = Number.parseInt(value, 10);
      id = Number.isNaN(parsed) ? null : parsed;
    } else if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }
  if (event === "message" && dataLines.length === 0) return null;
  return { id, event, data: dataLines.join("\n") };
}

export function toEnvelope(message: SseMessage): EventEnvelope | null {
  try {
    const parsed = JSON.parse(message.data) as Partial<EventEnvelope>;
    if (typeof parsed.seq !== "number") return null;
    return { ...(parsed as EventEnvelope), type: parsed.type ?? message.event };
  } catch {
    return null;
  }
}

/**
 * Drops anything already applied. The server skips duplicates too, but replay and live overlap by
 * design and a double-applied ITEM_READY would move a ticket that has come back.
 */
export function applyOrder(lastSeq: number, envelopes: EventEnvelope[]): EventEnvelope[] {
  let seen = lastSeq;
  const fresh: EventEnvelope[] = [];
  for (const envelope of [...envelopes].sort((a, b) => a.seq - b.seq)) {
    if (envelope.seq <= seen) continue;
    seen = envelope.seq;
    fresh.push(envelope);
  }
  return fresh;
}

/** Query keys a screen must refresh when this envelope lands. */
export function affectedQueries(envelope: EventEnvelope): string[] {
  const aggregate = envelope.aggregate_type as AggregateType;
  switch (aggregate) {
    case "ORDER":
      return ["kds", "tables", "bills", "order"];
    case "SESSION":
      return ["tables", "bills"];
    case "MENU_ITEM":
      return ["menu", "kds"];
    case "SHIFT":
      return ["shift"];
    default:
      return [];
  }
}

export const STREAM_SILENCE_MS = 40_000; // keepalives are every 15 s: three missed = dead
export const POLL_INTERVAL_MS = 3_000;
export const STREAM_RETRY_MS = 30_000;
export const OFFLINE_BANNER_AFTER_MS = 60_000;

export type ConnectionState = "connecting" | "live" | "polling" | "offline" | "signed-out";
