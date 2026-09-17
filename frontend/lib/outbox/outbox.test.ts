/**
 * Outbox drain, durability, backoff, and the Accra 30-minute-cut scenario.
 * fake-indexeddb stands in for the tablet's store; the scheduler is injected so
 * a half-hour outage is a few milliseconds of test time.
 */

import "fake-indexeddb/auto";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { backoffMs, BASE_BACKOFF_MS, MAX_BACKOFF_MS } from "./backoff";
import {
  appendCommand,
  closeOutboxDb,
  countEntries,
  getEntry,
  pendingEntries,
  resetOutboxDb,
} from "./db";
import { Outbox, CONFLICT_ATTEMPTS, type Scheduler, type Transport } from "./outbox";
import { classifyCommand } from "./policy";
import { OUTBOX_HEADER, QUEUED_STATUS, isQueued } from "./responses";
import type { OutboxCommand, OutboxEntry } from "./types";

function cmd(partial: Partial<OutboxCommand> & Pick<OutboxCommand, "id" | "path" | "idempotencyKey">): OutboxCommand {
  return {
    body: partial.body ?? { id: partial.id },
    clientTime: partial.clientTime ?? "2026-09-17T12:00:00.000Z",
    headers: partial.headers ?? {
      "idempotency-key": partial.idempotencyKey,
      "x-client-time": "2026-09-17T12:00:00.000Z",
    },
    ...partial,
  };
}

function okResponse(body: unknown = { ok: true }): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function manualScheduler(): Scheduler & { flush: () => void; pendingMs: () => number | null } {
  let next: { run: () => void; ms: number } | null = null;
  return {
    schedule(run, ms) {
      next = { run, ms };
    },
    cancel() {
      next = null;
    },
    flush() {
      const job = next;
      next = null;
      job?.run();
    },
    pendingMs() {
      return next?.ms ?? null;
    },
  };
}

beforeEach(async () => {
  await resetOutboxDb();
});

afterEach(async () => {
  await resetOutboxDb();
});

describe("backoffMs", () => {
  it("climbs 1s → 30s and caps", () => {
    expect(backoffMs(1)).toBe(BASE_BACKOFF_MS);
    expect(backoffMs(2)).toBe(2_000);
    expect(backoffMs(3)).toBe(4_000);
    expect(backoffMs(6)).toBe(MAX_BACKOFF_MS);
    expect(backoffMs(20)).toBe(MAX_BACKOFF_MS);
  });
});

describe("classifyCommand (money ops)", () => {
  it("queues additive kitchen commands", () => {
    expect(classifyCommand("/api/v1/orders").policy).toBe("queue");
    expect(classifyCommand("/api/v1/orders/abc/submit").policy).toBe("queue");
    expect(classifyCommand("/api/v1/sessions").policy).toBe("queue");
  });

  it("blocks payments, shifts and manager money moves offline", () => {
    for (const path of [
      "/api/v1/payments",
      "/api/v1/sessions/x/payments",
      "/api/v1/shifts/open",
      "/api/v1/shifts/y/close",
      "/api/v1/drawer/movements",
      "/api/v1/orders/z/discount",
      "/api/v1/orders/z/comp",
      "/api/v1/orders/z/void",
      "/api/v1/sessions/x/reopen",
    ]) {
      const rule = classifyCommand(path);
      expect(rule.policy).toBe("online-only");
      expect(rule.code).toBe("money_offline");
    }
  });

  it("blocks guest and auth surfaces from queuing", () => {
    expect(classifyCommand("/api/v1/guest/orders").code).toBe("guest_offline");
    expect(classifyCommand("/api/v1/auth/pin").code).toBe("auth_offline");
  });
});

describe("appendCommand", () => {
  it("enqueues with monotonic seq and stable idempotency key", async () => {
    const a = await appendCommand(cmd({ id: "a", path: "/api/v1/orders", idempotencyKey: "key-a" }));
    const b = await appendCommand(cmd({ id: "b", path: "/api/v1/orders", idempotencyKey: "key-b", body: { id: "b" } }));
    expect(a.appended).toBe(true);
    expect(b.appended).toBe(true);
    expect(a.entry.seq).toBe(1);
    expect(b.entry.seq).toBe(2);
    expect(a.entry.idempotencyKey).toBe("key-a");
    expect((await pendingEntries()).map((e) => e.id)).toEqual(["a", "b"]);
  });

  it("does not re-enqueue the same idempotency key", async () => {
    const first = await appendCommand(cmd({ id: "a", path: "/api/v1/orders", idempotencyKey: "same" }));
    const second = await appendCommand(cmd({ id: "a-dup", path: "/api/v1/orders", idempotencyKey: "same", body: { id: "other" } }));
    expect(first.appended).toBe(true);
    expect(second.appended).toBe(false);
    expect(second.entry.id).toBe("a");
    expect(await countEntries()).toEqual({ queued: 1, failed: 0 });
  });

  it("dedupes double-tap with same path and body", async () => {
    const body = { id: "order-1", session_id: "s1" };
    const first = await appendCommand(cmd({ id: "order-1", path: "/api/v1/orders", idempotencyKey: "k1", body }));
    const second = await appendCommand(cmd({ id: "order-1", path: "/api/v1/orders", idempotencyKey: "k2", body }));
    expect(first.appended).toBe(true);
    expect(second.appended).toBe(false);
    expect(await countEntries()).toEqual({ queued: 1, failed: 0 });
  });

  it("survives a simulated reload (durability)", async () => {
    await appendCommand(cmd({ id: "durable", path: "/api/v1/orders", idempotencyKey: "k-d" }));
    await closeOutboxDb();
    const entry = await getEntry("durable");
    expect(entry?.idempotencyKey).toBe("k-d");
    expect(entry?.status).toBe("queued");
  });
});

describe("Outbox drain", () => {
  it("drains five commands in FIFO order", async () => {
    const sent: string[] = [];
    const transport: Transport = async (entry) => {
      sent.push(entry.id);
      return okResponse({ id: entry.id });
    };
    const box = new Outbox({ transport, isOnline: () => true });

    const responses = await Promise.all(
      ["1", "2", "3", "4", "5"].map((id) =>
        box.submit(cmd({ id, path: `/api/v1/orders/${id}/submit`, idempotencyKey: `k-${id}` })),
      ),
    );

    expect(sent).toEqual(["1", "2", "3", "4", "5"]);
    expect(responses.every((r) => r.ok)).toBe(true);
    expect(await countEntries()).toEqual({ queued: 0, failed: 0 });
  });

  it("retries a mid-queue network failure without reordering", async () => {
    const sent: string[] = [];
    let failOnce = true;
    const scheduler = manualScheduler();
    const transport: Transport = async (entry) => {
      sent.push(entry.id);
      if (entry.id === "2" && failOnce) {
        failOnce = false;
        throw new Error("WAN down");
      }
      return okResponse({ id: entry.id });
    };
    const box = new Outbox({ transport, isOnline: () => true, scheduler });

    const p1 = box.submit(cmd({ id: "1", path: "/a", idempotencyKey: "k1" }));
    const p2 = box.submit(cmd({ id: "2", path: "/b", idempotencyKey: "k2" }));
    const p3 = box.submit(cmd({ id: "3", path: "/c", idempotencyKey: "k3" }));

    // First pass: 1 delivered, 2 deferred, 3 still waiting. Callers of 2/3 get 202.
    const r1 = await p1;
    expect(r1.ok).toBe(true);
    const r2 = await p2;
    const r3 = await p3;
    expect(isQueued(r2)).toBe(true);
    expect(isQueued(r3)).toBe(true);
    expect(sent).toEqual(["1", "2"]);
    expect(scheduler.pendingMs()).toBe(BASE_BACKOFF_MS);

    // Resume after backoff: 2 then 3, never 1 again.
    const p2b = box.submit(cmd({ id: "2", path: "/b", idempotencyKey: "k2" }));
    const p3b = box.submit(cmd({ id: "3", path: "/c", idempotencyKey: "k3" }));
    scheduler.flush();
    await box.drain();
    expect((await p2b).ok).toBe(true);
    expect((await p3b).ok).toBe(true);
    expect(sent).toEqual(["1", "2", "2", "3"]);
    expect(await countEntries()).toEqual({ queued: 0, failed: 0 });
  });

  it("keeps the same Idempotency-Key across retries (no duplicate on replay)", async () => {
    const keys: string[] = [];
    let attempts = 0;
    const scheduler = manualScheduler();
    const transport: Transport = async (entry) => {
      keys.push(entry.idempotencyKey);
      attempts += 1;
      if (attempts < 3) throw new Error("timeout");
      return okResponse();
    };
    const box = new Outbox({ transport, isOnline: () => true, scheduler });

    const first = box.submit(cmd({ id: "x", path: "/api/v1/orders", idempotencyKey: "stable-key" }));
    await first;
    expect(keys).toEqual(["stable-key"]);

    const second = box.submit(cmd({ id: "x", path: "/api/v1/orders", idempotencyKey: "stable-key" }));
    scheduler.flush();
    await second;
    // Still queued after second failure — flush again.
    const third = box.submit(cmd({ id: "x", path: "/api/v1/orders", idempotencyKey: "stable-key" }));
    scheduler.flush();
    expect((await third).ok).toBe(true);
    expect(keys).toEqual(["stable-key", "stable-key", "stable-key"]);
    expect(await countEntries()).toEqual({ queued: 0, failed: 0 });
  });

  it("marks hard 4xx as failed and surfaces them", async () => {
    const transport: Transport = async () =>
      new Response(JSON.stringify({ detail: "void rejected", code: "illegal_transition", status: 422, title: "Nope", type: "about:blank", errors: {} }), {
        status: 422,
        headers: { "Content-Type": "application/problem+json" },
      });
    const box = new Outbox({ transport, isOnline: () => true });
    const response = await box.submit(cmd({ id: "void-1", path: "/api/v1/orders/1/note", idempotencyKey: "k-void" }));
    expect(response.status).toBe(422);
    expect(await countEntries()).toEqual({ queued: 0, failed: 1 });
    const entry = await getEntry("void-1");
    expect(entry?.status).toBe("failed");
    expect(entry?.lastError).toContain("void rejected");
  });

  it("gives up after CONFLICT_ATTEMPTS of 409/429", async () => {
    const scheduler = manualScheduler();
    const transport: Transport = async () => new Response("conflict", { status: 409 });
    const box = new Outbox({ transport, isOnline: () => true, scheduler });

    for (let i = 0; i < CONFLICT_ATTEMPTS; i += 1) {
      const pending = box.submit(cmd({ id: "c1", path: "/api/v1/orders", idempotencyKey: "k-c" }));
      if (i > 0) scheduler.flush();
      await pending;
    }
    expect(await countEntries()).toEqual({ queued: 0, failed: 1 });
  });
});

describe("30-minute cut", () => {
  it("holds every command through a long outage and delivers each exactly once after reconnect", async () => {
    const delivered: OutboxEntry[] = [];
    // Accra shape: the tablet thinks it is online (LAN/router up) but the WAN is dead.
    let wanUp = false;
    const scheduler = manualScheduler();
    const transport: Transport = async (entry) => {
      if (!wanUp) throw new Error("no WAN");
      delivered.push(entry);
      return okResponse({ id: entry.id });
    };
    const box = new Outbox({ transport, isOnline: () => true, scheduler });

    // Service during the cut: five kitchen commands land in IndexedDB.
    const ids = ["o1", "o2", "o3", "o4", "o5"];
    const queuedResponses = await Promise.all(
      ids.map((id) => box.submit(cmd({ id, path: `/api/v1/orders/${id}/submit`, idempotencyKey: `idem-${id}` }))),
    );
    expect(queuedResponses.every((r) => r.status === QUEUED_STATUS)).toBe(true);
    expect(queuedResponses.every((r) => r.headers.get(OUTBOX_HEADER) === "queued")).toBe(true);
    expect(await countEntries()).toEqual({ queued: 5, failed: 0 });
    expect(delivered).toEqual([]);

    // Half-hour of backoff while the WAN stays dead — nothing leaves the building.
    for (let tick = 0; tick < 12; tick += 1) {
      expect(scheduler.pendingMs()).toBeLessThanOrEqual(MAX_BACKOFF_MS);
      scheduler.flush();
      await box.drain();
    }
    expect(delivered).toEqual([]);
    expect((await pendingEntries()).map((e) => e.id)).toEqual(ids);
    // Keys never rotated during the outage.
    expect((await pendingEntries()).map((e) => e.idempotencyKey)).toEqual(ids.map((id) => `idem-${id}`));

    // WAN returns: drain FIFO, each key once.
    wanUp = true;
    await box.resume();
    expect(delivered.map((e) => e.id)).toEqual(ids);
    expect(delivered.map((e) => e.idempotencyKey)).toEqual(ids.map((id) => `idem-${id}`));
    expect(await countEntries()).toEqual({ queued: 0, failed: 0 });
  });
});

describe("snapshot / subscribe", () => {
  it("publishes queued counts for the badge", async () => {
    const snapshots: number[] = [];
    const box = new Outbox({
      transport: async () => {
        throw new Error("offline");
      },
      isOnline: () => false,
    });
    box.subscribe((s) => snapshots.push(s.queued));
    await box.submit(cmd({ id: "q1", path: "/api/v1/orders", idempotencyKey: "kq" }));
    expect(snapshots.at(-1)).toBe(1);
  });
});

// Silence unused vi import if tree-shaken differently across versions.
void vi;
