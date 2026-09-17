/**
 * The durable half of the outbox. IndexedDB, not localStorage: a command survives a reload, a
 * crashed tab, a flat battery and the tablet being closed for the night.
 *
 * Only this file talks to `idb`. Everything above it works on `OutboxEntry` values.
 */

import { deleteDB, openDB, type DBSchema, type IDBPDatabase } from "idb";

import type { OutboxCommand, OutboxEntry, OutboxStatus } from "./types";

export const DB_NAME = "renzy-outbox";
export const DB_VERSION = 1;

const SEQ_KEY = "seq";

interface OutboxDb extends DBSchema {
  outbox: {
    key: string;
    value: OutboxEntry;
    indexes: { seq: number };
  };
  meta: {
    key: string;
    value: number;
  };
}

let handle: Promise<IDBPDatabase<OutboxDb>> | null = null;

function db(): Promise<IDBPDatabase<OutboxDb>> {
  handle ??= openDB<OutboxDb>(DB_NAME, DB_VERSION, {
    upgrade(database) {
      const store = database.createObjectStore("outbox", { keyPath: "id" });
      store.createIndex("seq", "seq");
      database.createObjectStore("meta");
    },
  });
  return handle;
}

/** Drop the database and the cached handle. Tests only — service never calls this. */
export async function resetOutboxDb(): Promise<void> {
  if (handle) {
    (await handle).close();
    handle = null;
  }
  await deleteDB(DB_NAME);
}

function isPending(status: OutboxStatus): boolean {
  // `sending` counts as pending: a tab killed mid-flight leaves one behind, and the
  // Idempotency-Key is exactly what makes re-sending it safe.
  return status !== "failed";
}

/**
 * Write a command to the queue and give it the next seq. The seq counter and the entry are written
 * in one transaction so two commands enqueued in the same tick cannot share a number.
 *
 * Returns the existing entry, and `false`, when this command is already queued — either the same
 * Idempotency-Key or the same path and body. That second clause is the double-tap guard: a waiter
 * hammering "Send" on a dead connection produces one ticket, not four.
 */
export async function appendCommand(
  command: OutboxCommand,
): Promise<{ entry: OutboxEntry; appended: boolean }> {
  const database = await db();
  const tx = database.transaction(["outbox", "meta"], "readwrite");
  const store = tx.objectStore("outbox");
  const meta = tx.objectStore("meta");

  const fingerprint = commandFingerprint(command.path, command.body);
  for (const existing of await store.getAll()) {
    if (!isPending(existing.status)) continue;
    if (
      existing.idempotencyKey === command.idempotencyKey ||
      commandFingerprint(existing.path, existing.body) === fingerprint
    ) {
      await tx.done;
      return { entry: existing, appended: false };
    }
  }

  const seq = ((await meta.get(SEQ_KEY)) ?? 0) + 1;
  const entry: OutboxEntry = {
    id: command.id,
    seq,
    method: "POST",
    path: command.path,
    body: command.body,
    idempotencyKey: command.idempotencyKey,
    clientTime: command.clientTime,
    status: "queued",
    attempts: 0,
    lastError: null,
    failedStatus: null,
    headers: command.headers,
    conflicts: 0,
  };
  await meta.put(seq, SEQ_KEY);
  await store.put(entry);
  await tx.done;
  return { entry, appended: true };
}

function commandFingerprint(path: string, body: unknown): string {
  return `${path}\u0000${JSON.stringify(body ?? null)}`;
}

export async function putEntry(entry: OutboxEntry): Promise<void> {
  await (await db()).put("outbox", entry);
}

export async function deleteEntry(id: string): Promise<void> {
  await (await db()).delete("outbox", id);
}

export async function getEntry(id: string): Promise<OutboxEntry | undefined> {
  return (await db()).get("outbox", id);
}

/** Everything still to send, oldest first. Failed entries are out of the drain path. */
export async function pendingEntries(): Promise<OutboxEntry[]> {
  const rows = await (await db()).getAllFromIndex("outbox", "seq");
  return rows.filter((row) => isPending(row.status));
}

export async function headPending(): Promise<OutboxEntry | undefined> {
  return (await pendingEntries())[0];
}

export async function failedEntries(): Promise<OutboxEntry[]> {
  const rows = await (await db()).getAllFromIndex("outbox", "seq");
  return rows.filter((row) => row.status === "failed");
}

export async function countEntries(): Promise<{ queued: number; failed: number }> {
  const rows = await (await db()).getAllFromIndex("outbox", "seq");
  let queued = 0;
  let failed = 0;
  for (const row of rows) {
    if (row.status === "failed") failed += 1;
    else queued += 1;
  }
  return { queued, failed };
}

/** Put every failed entry back at its original place in the queue. Drives the badge's "Retry". */
export async function requeueFailed(): Promise<number> {
  const rows = await failedEntries();
  for (const row of rows) {
    await putEntry({ ...row, status: "queued", conflicts: 0, failedStatus: null });
  }
  return rows.length;
}

/**
 * Drop the failed entries from this device's queue. Safe in a way that `DELETE` on a domain table
 * is not: a failed entry is a command the server never accepted, so there is nothing to erase.
 */
export async function discardFailed(): Promise<number> {
  const rows = await failedEntries();
  for (const row of rows) await deleteEntry(row.id);
  return rows.length;
}
