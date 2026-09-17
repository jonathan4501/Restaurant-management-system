/**
 * The drain. FIFO, one command in flight, exponential backoff, resumes on reconnect.
 *
 * The contract with a caller is the honest one: `submit` resolves with the server's response if
 * the command got through, with the server's error if the server rejected it, and with a 202
 * "queued" if it is still on the device. It never resolves with a fabricated success.
 *
 * Everything that talks to the outside world — the transport, the online check, the backoff
 * timer — is injected, so the tests drive a 30-minute outage in a few milliseconds without fake
 * timers fighting IndexedDB.
 */

import { backoffMs } from "./backoff";
import {
  appendCommand,
  countEntries,
  deleteEntry,
  discardFailed,
  headPending,
  putEntry,
  requeueFailed,
} from "./db";
import { queuedResponse } from "./responses";
import type { OutboxCommand, OutboxEntry, OutboxSnapshot } from "./types";

/** Sends one entry. Rejects only when the request never reached a server. */
export type Transport = (entry: OutboxEntry) => Promise<Response>;

export interface Scheduler {
  /** Replaces any timer already pending. */
  schedule: (run: () => void, ms: number) => void;
  cancel: () => void;
}

export interface OutboxOptions {
  transport: Transport;
  isOnline: () => boolean;
  scheduler?: Scheduler;
}

/**
 * How many 409/429 answers an entry gets before it is marked failed and shown to a human. The
 * server is reachable and refusing, so waiting longer will not change its mind; a void the server
 * rejected has to be seen, not retried into the night.
 */
export const CONFLICT_ATTEMPTS = 3;

function timeoutScheduler(): Scheduler {
  let timer: ReturnType<typeof setTimeout> | null = null;
  return {
    schedule(run, ms) {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        run();
      }, ms);
    },
    cancel() {
      if (timer) clearTimeout(timer);
      timer = null;
    },
  };
}

type Outcome =
  | { kind: "delivered"; response: Response }
  | { kind: "failed"; response: Response }
  | { kind: "defer"; attempts: number };

interface Waiter {
  entry: OutboxEntry;
  resolvers: ((response: Response) => void)[];
}

export class Outbox {
  private readonly transport: Transport;
  private readonly isOnline: () => boolean;
  private readonly scheduler: Scheduler;
  private readonly listeners = new Set<(snapshot: OutboxSnapshot) => void>();
  private readonly waiters = new Map<string, Waiter>();

  private running: Promise<void> | null = null;
  private rerun = false;
  private backingOff = false;
  private current: OutboxSnapshot = { queued: 0, failed: 0, online: true };

  constructor({ transport, isOnline, scheduler }: OutboxOptions) {
    this.transport = transport;
    this.isOnline = isOnline;
    this.scheduler = scheduler ?? timeoutScheduler();
  }

  snapshot(): OutboxSnapshot {
    return this.current;
  }

  subscribe(listener: (snapshot: OutboxSnapshot) => void): () => void {
    this.listeners.add(listener);
    listener(this.current);
    return () => {
      this.listeners.delete(listener);
    };
  }

  /**
   * Write the command down, then try to send it. Resolves as soon as this command's fate is known
   * or the queue stops moving, whichever comes first — a caller is never made to wait out someone
   * else's backoff.
   */
  async submit(command: OutboxCommand): Promise<Response> {
    const { entry } = await appendCommand(command);
    const promise = new Promise<Response>((resolve) => {
      const waiter = this.waiters.get(entry.id) ?? { entry, resolvers: [] };
      waiter.entry = entry;
      waiter.resolvers.push(resolve);
      this.waiters.set(entry.id, waiter);
    });
    void this.drain();
    return promise;
  }

  /** Runs the queue until it is empty, blocked on the network, or waiting out a backoff. */
  drain(): Promise<void> {
    if (this.running) {
      this.rerun = true;
      return this.running;
    }
    if (this.backingOff) return this.settleAll();
    this.running = (async () => {
      try {
        do {
          this.rerun = false;
          await this.loop();
        } while (this.rerun && !this.backingOff);
        // Submitted while the queue was stopping: tell that caller it is queued rather than
        // leaving "Send" spinning until the backoff timer comes round.
        if (this.rerun) await this.settleAll();
      } finally {
        this.running = null;
      }
    })();
    return this.running;
  }

  /** Reconnected: cancel the backoff and go now rather than waiting out the remaining 29 seconds. */
  resume(): Promise<void> {
    this.scheduler.cancel();
    this.backingOff = false;
    return this.drain();
  }

  async retryFailed(): Promise<void> {
    await requeueFailed();
    await this.resume();
  }

  async discardFailed(): Promise<void> {
    await discardFailed();
    await this.publish();
  }

  /** Recompute the counts from the store and tell the badge. */
  async publish(): Promise<void> {
    const { queued, failed } = await countEntries();
    this.emit({ queued, failed, online: this.isOnline() });
  }

  private emit(snapshot: OutboxSnapshot): void {
    this.current = snapshot;
    for (const listener of this.listeners) listener(snapshot);
  }

  private async loop(): Promise<void> {
    if (this.backingOff) {
      await this.settleAll();
      return;
    }
    for (;;) {
      const entry = await headPending();
      if (!entry || !this.isOnline()) {
        await this.settleAll();
        return;
      }
      const outcome = await this.attempt(entry);
      if (outcome.kind === "defer") {
        this.backingOff = true;
        this.scheduler.schedule(() => {
          this.backingOff = false;
          void this.drain();
        }, backoffMs(outcome.attempts));
        await this.settleAll();
        return;
      }
      this.settle(entry.id, outcome.response);
      await this.publish();
    }
  }

  private async attempt(entry: OutboxEntry): Promise<Outcome> {
    const sending: OutboxEntry = { ...entry, status: "sending", attempts: entry.attempts + 1 };
    await putEntry(sending);
    await this.publish();

    let response: Response;
    try {
      response = await this.transport(sending);
    } catch (error) {
      // Never reached a server. This is the 30-minute-cut case: keep it, keep its place, retry.
      await putEntry({ ...sending, status: "queued", lastError: describe(error) });
      return { kind: "defer", attempts: sending.attempts };
    }

    if (response.ok) {
      await deleteEntry(entry.id);
      return { kind: "delivered", response };
    }

    if (response.status === 409 || response.status === 429) {
      const conflicts = sending.conflicts + 1;
      if (conflicts < CONFLICT_ATTEMPTS) {
        await putEntry({
          ...sending,
          status: "queued",
          conflicts,
          lastError: `HTTP ${response.status}`,
        });
        return { kind: "defer", attempts: sending.attempts };
      }
      await putEntry({
        ...sending,
        status: "failed",
        conflicts,
        failedStatus: response.status,
        lastError: await detail(response),
      });
      return { kind: "failed", response };
    }

    if (response.status >= 400 && response.status < 500) {
      // The server understood and said no. Silently dropping this would hide a rejected void.
      await putEntry({
        ...sending,
        status: "failed",
        failedStatus: response.status,
        lastError: await detail(response),
      });
      return { kind: "failed", response };
    }

    await putEntry({ ...sending, status: "queued", lastError: `HTTP ${response.status}` });
    return { kind: "defer", attempts: sending.attempts };
  }

  private settle(id: string, response: Response): void {
    const waiter = this.waiters.get(id);
    if (!waiter) return;
    this.waiters.delete(id);
    // One Response body can only be read once, and two call sites may be waiting on a de-duplicated
    // command, so each gets its own clone.
    for (const resolve of waiter.resolvers) resolve(response.clone());
  }

  /** The queue stopped moving. Everyone still waiting is, truthfully, still queued. */
  private async settleAll(): Promise<void> {
    await this.publish();
    const waiting = [...this.waiters.values()];
    this.waiters.clear();
    for (const waiter of waiting) {
      for (const resolve of waiter.resolvers) resolve(queuedResponse(waiter.entry));
    }
  }
}

function describe(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return String(error);
}

async function detail(response: Response): Promise<string> {
  try {
    const body = (await response.clone().json()) as { detail?: string; title?: string };
    return body.detail || body.title || `HTTP ${response.status}`;
  } catch {
    return `HTTP ${response.status}`;
  }
}
