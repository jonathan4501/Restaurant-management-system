"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EightySixSheet } from "@/components/kds/EightySixSheet";
import { TicketCard } from "@/components/kds/TicketCard";
import { api } from "@/lib/api/client";
import type { KdsTicket, TicketLine } from "@/lib/domain";
import {
  ackTicket,
  markAllReady,
  markLineReady,
  patchTicket,
  removeTicket,
  serverNowIso,
} from "@/lib/kds/board";
import { useEventStream } from "@/lib/realtime/useEventStream";
import { useStaff } from "@/lib/stores/staff";

const STATIONS = ["ALL", "KITCHEN", "GRILL", "BAR"] as const;
type Station = (typeof STATIONS)[number];
const STATION_KEY = "renzy.kds.station";

const COLUMNS: { key: KdsTicket["status"]; label: string }[] = [
  { key: "SUBMITTED", label: "New" },
  { key: "PREPARING", label: "Preparing" },
  { key: "READY", label: "Ready" },
];

/** A short chime. Browsers block autoplay until the cook has tapped once, hence the enable button. */
function useChime() {
  const context = useRef<AudioContext | null>(null);
  return useCallback(() => {
    try {
      context.current ??= new AudioContext();
      const ctx = context.current;
      const oscillator = ctx.createOscillator();
      const gain = ctx.createGain();
      oscillator.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.2, ctx.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.45);
      oscillator.connect(gain).connect(ctx.destination);
      oscillator.start();
      oscillator.stop(ctx.currentTime + 0.5);
    } catch {
      /* no audio device, or the browser said no — the screen still works */
    }
  }, []);
}

export function KdsBoard() {
  const queryClient = useQueryClient();
  const staff = useStaff((s) => s.staff);
  const [station, setStation] = useState<Station>("ALL");
  const [now, setNow] = useState(() => Date.now());
  const [soundOn, setSoundOn] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const chime = useChime();

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(STATION_KEY) as Station | null;
      if (saved && STATIONS.includes(saved)) setStation(saved);
    } catch {
      /* storage disabled */
    }
  }, []);

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(id);
  }, [toast]);

  const stream = useEventStream({
    onEvent: (envelope) => {
      if (soundOn && envelope.type === "ORDER_SUBMITTED") chime();
    },
  });

  const tickets = useQuery({
    queryKey: ["kds", station],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/v1/kds/tickets", {
        params: { query: station === "ALL" ? {} : { station } },
      });
      if (error) throw error;
      return (Array.isArray(data) ? data : []) as unknown as KdsTicket[];
    },
    refetchInterval: stream.state === "live" ? false : 10_000,
  });

  /**
   * Move the card now, keep it outlined as pending, then let the read (or the stream) settle it.
   * The command itself is idempotent — lib/api/client adds an Idempotency-Key to every POST — so a
   * double tap on a slow connection cannot ack twice.
   */
  const command = useCallback(
    async (
      orderId: string,
      optimistic: (rows: KdsTicket[]) => KdsTicket[],
      run: () => Promise<{ error?: unknown }>,
    ) => {
      setPending((p) => ({ ...p, [orderId]: true }));
      queryClient.setQueryData<KdsTicket[]>(["kds", station], (rows) =>
        rows ? optimistic(rows) : rows,
      );
      try {
        const { error } = await run();
        if (error) setToast("That did not go through. Try again.");
      } catch {
        setToast("That did not go through. Try again.");
      } finally {
        await queryClient.invalidateQueries({ queryKey: ["kds"] });
        setPending((p) => ({ ...p, [orderId]: false }));
      }
    },
    [queryClient, station],
  );

  const onAck = useCallback(
    (ticket: KdsTicket) => {
      const at = serverNowIso(stream.serverOffsetMs);
      void command(
        ticket.order_id,
        (rows) => patchTicket(rows, ticket.order_id, (t) => ackTicket(t, at)),
        () =>
          api.POST("/api/v1/orders/{order_id}/ack", {
            params: { path: { order_id: ticket.order_id } },
          }),
      );
    },
    [command, stream.serverOffsetMs],
  );

  const onAllReady = useCallback(
    (ticket: KdsTicket) => {
      const at = serverNowIso(stream.serverOffsetMs);
      void command(
        ticket.order_id,
        (rows) => patchTicket(rows, ticket.order_id, (t) => markAllReady(t, at)),
        () =>
          api.POST("/api/v1/orders/{order_id}/ready", {
            params: { path: { order_id: ticket.order_id } },
          }),
      );
    },
    [command, stream.serverOffsetMs],
  );

  const onLineReady = useCallback(
    (ticket: KdsTicket, line: TicketLine) => {
      const at = serverNowIso(stream.serverOffsetMs);
      void command(
        ticket.order_id,
        (rows) => patchTicket(rows, ticket.order_id, (t) => markLineReady(t, line.item_id, at)),
        () =>
          api.POST("/api/v1/orders/{order_id}/items/{item_id}/ready", {
            params: { path: { order_id: ticket.order_id, item_id: line.item_id } },
          }),
      );
    },
    [command, stream.serverOffsetMs],
  );

  const onServed = useCallback(
    (ticket: KdsTicket) =>
      void command(
        ticket.order_id,
        (rows) => removeTicket(rows, ticket.order_id),
        () =>
          api.POST("/api/v1/orders/{order_id}/serve", {
            params: { path: { order_id: ticket.order_id } },
          }),
      ),
    [command],
  );

  const columns = useMemo(() => {
    const rows = tickets.data ?? [];
    return COLUMNS.map((column) => ({
      ...column,
      tickets: rows.filter((t) => t.status === column.key),
    }));
  }, [tickets.data]);

  function pickStation(next: Station) {
    setStation(next);
    try {
      window.localStorage.setItem(STATION_KEY, next);
    } catch {
      /* storage disabled */
    }
  }

  return (
    <main className="staff-shell staff-theme flex h-screen flex-col overflow-hidden" data-testid="kds">
      {stream.stale ? (
        <div
          data-testid="kds-offline"
          className="bg-[var(--danger)] px-4 py-3 text-center text-xl font-bold text-[#2a0d0b]"
        >
          OFFLINE — check the printer for tickets
        </div>
      ) : null}

      <header className="flex items-center justify-between gap-4 border-b border-[var(--line)] px-4 py-3">
        <div className="flex items-center gap-2" role="tablist" data-testid="station-filter">
          {STATIONS.map((option) => (
            <button
              key={option}
              type="button"
              role="tab"
              aria-selected={station === option}
              data-testid={`station-${option.toLowerCase()}`}
              onClick={() => pickStation(option)}
              className={`min-h-14 rounded-lg px-5 text-lg font-semibold ${
                station === option
                  ? "bg-[var(--accent)] text-[var(--accent-ink)]"
                  : "border border-[var(--line)] bg-[var(--surface-2)] text-[var(--ink-2)]"
              }`}
            >
              {option === "ALL" ? "All stations" : option}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <span
            data-testid="kds-connection"
            data-state={stream.state}
            className="rounded-full border border-[var(--line)] px-3 py-1 text-sm text-[var(--ink-3)]"
          >
            {stream.state === "live" ? "Live" : stream.state === "polling" ? "Catching up" : stream.state}
          </span>
          <button
            type="button"
            data-testid="kds-sound"
            aria-pressed={soundOn}
            onClick={() => {
              const next = !soundOn;
              setSoundOn(next);
              if (next) chime(); // the tap is the gesture the browser wants, and it proves it works
            }}
            className={`min-h-14 rounded-lg border px-4 text-lg ${
              soundOn
                ? "border-[var(--accent-line)] text-[var(--accent)]"
                : "border-[var(--line)] text-[var(--ink-3)]"
            }`}
          >
            {soundOn ? "Chime on" : "Chime off"}
          </button>
          <button
            type="button"
            data-testid="kds-86"
            onClick={() => setSheetOpen(true)}
            className="min-h-14 rounded-lg border-2 border-[var(--danger)] px-5 text-lg font-bold text-[var(--danger)]"
          >
            86
          </button>
          <span className="text-lg text-[var(--ink-3)]">{staff?.name ?? "Kitchen"}</span>
        </div>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-3 overflow-hidden p-3 lg:grid-cols-3">
        {columns.map((column) => (
          <section
            key={column.key}
            data-testid={`column-${column.key}`}
            className="flex min-h-0 flex-col rounded-lg bg-[var(--surface-2)]"
          >
            <h2 className="flex items-baseline justify-between border-b border-[var(--line)] px-4 py-2 text-lg font-bold uppercase tracking-wide">
              {column.label}
              <span className="num text-[var(--ink-3)]">{column.tickets.length}</span>
            </h2>
            <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
              {column.tickets.map((ticket) => (
                <TicketCard
                  key={ticket.order_id}
                  ticket={ticket}
                  now={now}
                  offsetMs={stream.serverOffsetMs}
                  pending={Boolean(pending[ticket.order_id])}
                  onAck={onAck}
                  onLineReady={onLineReady}
                  onAllReady={onAllReady}
                  onServed={onServed}
                />
              ))}
              {column.tickets.length === 0 ? (
                <p className="px-2 py-6 text-center text-lg text-[var(--ink-3)]">Nothing here</p>
              ) : null}
            </div>
          </section>
        ))}
      </div>

      {toast ? (
        <div
          data-testid="kds-toast"
          role="status"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl bg-[var(--accent)] px-8 py-4 text-2xl font-bold text-[var(--accent-ink)]"
        >
          {toast}
        </div>
      ) : null}

      <EightySixSheet open={sheetOpen} onClose={() => setSheetOpen(false)} onDone={setToast} />
    </main>
  );
}
