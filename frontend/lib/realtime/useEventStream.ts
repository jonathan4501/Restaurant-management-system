"use client";

/**
 * The live connection every staff screen shares. Implements lib/realtime/README.md:
 * stream first, dedupe by seq, two failures → poll, RESYNC → refetch, AUTH_EXPIRED → login.
 *
 * EventSource cannot carry the device and staff headers, so the stream is a fetch whose body we
 * read as it arrives.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { API_BASE_URL } from "@/lib/api/client";
import { tokens } from "@/lib/auth/tokens";
import type { EventEnvelope } from "@/lib/domain";
import { serverOffsetMs } from "@/lib/kds/urgency";
import {
  applyOrder,
  affectedQueries,
  OFFLINE_BANNER_AFTER_MS,
  POLL_INTERVAL_MS,
  SseParser,
  STREAM_RETRY_MS,
  STREAM_SILENCE_MS,
  toEnvelope,
  type ConnectionState,
} from "./sse";

interface Options {
  /** Called for every new envelope, in seq order, after dedupe. */
  onEvent?: (envelope: EventEnvelope) => void;
  /** RESYNC: the client missed too much to replay. Refetch everything on screen. */
  onResync?: () => void;
  enabled?: boolean;
}

export interface StreamStatus {
  state: ConnectionState;
  lastSeq: number;
  serverOffsetMs: number;
  /** True once the screen has had no successful contact for a minute — show the paper-tickets banner. */
  stale: boolean;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  const device = tokens.device();
  const session = tokens.session();
  if (device) headers["X-Device-Token"] = device;
  if (session) headers["Authorization"] = `Bearer ${session}`;
  return headers;
}

export function useEventStream({ onEvent, onResync, enabled = true }: Options = {}): StreamStatus {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [state, setState] = useState<ConnectionState>("connecting");
  const [stale, setStale] = useState(false);
  const [offset, setOffset] = useState(0);
  const lastSeq = useRef(0);
  const failures = useRef(0);
  const lastContact = useRef(Date.now());
  const handlers = useRef({ onEvent, onResync });
  handlers.current = { onEvent, onResync };

  const deliver = useCallback(
    (envelopes: EventEnvelope[]) => {
      const fresh = applyOrder(lastSeq.current, envelopes);
      if (fresh.length === 0) return;
      lastSeq.current = fresh[fresh.length - 1]!.seq;
      const keys = new Set<string>();
      for (const envelope of fresh) {
        handlers.current.onEvent?.(envelope);
        for (const key of affectedQueries(envelope)) keys.add(key);
      }
      for (const key of keys) void queryClient.invalidateQueries({ queryKey: [key] });
    },
    [queryClient],
  );

  const signedOut = useCallback(() => {
    setState("signed-out");
    tokens.setSession(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let polling = false;
    let pollTimer: ReturnType<typeof setTimeout> | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const markContact = () => {
      lastContact.current = Date.now();
      setStale(false);
      failures.current = 0;
    };

    const stopPolling = () => {
      polling = false;
      if (pollTimer) {
        clearTimeout(pollTimer);
        pollTimer = null;
      }
    };

    async function poll(): Promise<void> {
      if (stopped || !polling) return;
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/v1/events?since=${lastSeq.current}&limit=200`,
          { headers: authHeaders(), cache: "no-store" },
        );
        if (response.status === 401 || response.status === 403) return signedOut();
        if (!response.ok) throw new Error(`events ${response.status}`);
        setOffset(serverOffsetMs(response.headers.get("Date")));
        const body = (await response.json()) as {
          events: EventEnvelope[];
          last_seq: number;
          has_more?: boolean;
        };
        deliver(body.events ?? []);
        // last_seq counts events this role may not see; without it a kitchen poller would stick.
        if (typeof body.last_seq === "number" && body.last_seq > lastSeq.current) {
          lastSeq.current = body.last_seq;
        }
        markContact();
        setState("polling");
        if (body.has_more) return void poll();
      } catch {
        if (Date.now() - lastContact.current > OFFLINE_BANNER_AFTER_MS) {
          setStale(true);
          setState("offline");
        }
      }
      if (!stopped && polling) pollTimer = setTimeout(() => void poll(), POLL_INTERVAL_MS);
    }

    const startPolling = () => {
      if (polling) return; // one poll loop, however many times the stream has failed
      polling = true;
      setState("polling");
      void poll();
    };

    async function readStream(): Promise<void> {
      if (stopped) return;
      controller = new AbortController();
      const silence = setInterval(() => {
        if (Date.now() - lastContact.current > STREAM_SILENCE_MS) controller?.abort();
      }, 5_000);
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/stream`, {
          headers: {
            ...authHeaders(),
            Accept: "text/event-stream",
            ...(lastSeq.current ? { "Last-Event-ID": String(lastSeq.current) } : {}),
          },
          signal: controller.signal,
          cache: "no-store",
        });
        if (response.status === 401 || response.status === 403) {
          clearInterval(silence);
          return signedOut();
        }
        if (!response.ok || !response.body) throw new Error(`stream ${response.status}`);

        setOffset(serverOffsetMs(response.headers.get("Date")));
        markContact();
        stopPolling(); // the stream is back; two pollers would double-count nothing but bandwidth
        setState("live");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        const parser = new SseParser();
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          markContact();
          for (const message of parser.push(decoder.decode(value, { stream: true }))) {
            if (message.event === "AUTH_EXPIRED") {
              clearInterval(silence);
              return signedOut();
            }
            if (message.event === "RESYNC") {
              const seq = Number(message.id ?? 0);
              if (seq > lastSeq.current) lastSeq.current = seq;
              handlers.current.onResync?.();
              void queryClient.invalidateQueries();
              continue;
            }
            const envelope = toEnvelope(message);
            if (envelope) deliver([envelope]);
          }
        }
        throw new Error("stream ended");
      } catch {
        if (stopped) return;
        failures.current += 1;
        if (Date.now() - lastContact.current > OFFLINE_BANNER_AFTER_MS) {
          setStale(true);
          setState("offline");
        }
        // Two failures in a row: stop hammering the stream, poll instead and retry it slowly.
        if (failures.current >= 2) {
          startPolling();
          retryTimer = setTimeout(() => void readStream(), STREAM_RETRY_MS);
          return;
        }
        retryTimer = setTimeout(() => void readStream(), 1_000);
      } finally {
        clearInterval(silence);
      }
    }

    void readStream();
    return () => {
      stopped = true;
      controller?.abort();
      if (pollTimer) clearTimeout(pollTimer);
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [enabled, deliver, signedOut, queryClient]);

  return { state, lastSeq: lastSeq.current, serverOffsetMs: offset, stale };
}
