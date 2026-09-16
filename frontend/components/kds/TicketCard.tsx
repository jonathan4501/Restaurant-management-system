"use client";

import type { KdsTicket, TicketLine } from "@/lib/domain";
import { ageSeconds, formatAge, ticketClockStart, urgencyFor, type Urgency } from "@/lib/kds/urgency";

const BORDER: Record<Urgency, string> = {
  fresh: "border-[var(--line)]",
  warning: "border-[var(--warn)]",
  late: "border-[var(--danger)] kds-late",
};

const AGE_COLOUR: Record<Urgency, string> = {
  fresh: "text-[var(--ink-2)]",
  warning: "text-[var(--warn)]",
  late: "text-[var(--danger)]",
};

interface TicketCardProps {
  ticket: KdsTicket;
  now: number;
  offsetMs: number;
  pending: boolean;
  onAck: (ticket: KdsTicket) => void;
  onLineReady: (ticket: KdsTicket, line: TicketLine) => void;
  onAllReady: (ticket: KdsTicket) => void;
  onServed: (ticket: KdsTicket) => void;
}

export function TicketCard({
  ticket,
  now,
  offsetMs,
  pending,
  onAck,
  onLineReady,
  onAllReady,
  onServed,
}: TicketCardProps) {
  const seconds = ageSeconds(ticketClockStart(ticket), now, offsetMs);
  const urgency = urgencyFor(seconds);

  return (
    <article
      data-testid={`ticket-${ticket.order_number}`}
      data-urgency={urgency}
      data-status={ticket.status}
      className={`rounded-xl border-2 bg-[var(--surface)] ${BORDER[urgency]} ${pending ? "opacity-60 outline-dashed outline-2 outline-[var(--accent-line)]" : ""}`}
    >
      <header className="flex items-baseline justify-between gap-3 border-b border-[var(--line)] px-4 py-3">
        <div className="flex items-baseline gap-3">
          <span className="num text-3xl font-bold">#{ticket.order_number ?? "—"}</span>
          <span className="text-xl text-[var(--ink-2)]">Table {ticket.table_number}</span>
        </div>
        <span
          data-testid={`ticket-age-${ticket.order_number}`}
          className={`num text-3xl font-bold tabular-nums ${AGE_COLOUR[urgency]}`}
        >
          {formatAge(seconds)}
        </span>
      </header>

      <ul className="flex flex-col gap-1 px-2 py-2">
        {ticket.items.map((line) => {
          const done = line.status === "READY" || line.status === "SERVED";
          return (
            <li key={line.item_id}>
              <button
                type="button"
                data-testid={`line-${line.item_id}`}
                data-done={done}
                disabled={done || ticket.status === "SUBMITTED"}
                onClick={() => onLineReady(ticket, line)}
                className={`flex w-full items-start gap-3 rounded-lg px-2 py-2 text-left disabled:cursor-default ${
                  done ? "opacity-45 line-through" : "active:bg-[var(--surface-3)]"
                }`}
              >
                <span className="num min-w-9 text-2xl font-bold">{line.quantity}×</span>
                <span className="flex-1">
                  <span className="block text-2xl font-semibold leading-tight">{line.name}</span>
                  {line.modifiers.length > 0 ? (
                    <span className="block text-lg font-medium text-[var(--accent)]">
                      {line.modifiers.map((m) => m.name).join(" · ")}
                    </span>
                  ) : null}
                  {line.notes ? (
                    <span className="block text-lg italic text-[var(--warn)]">{line.notes}</span>
                  ) : null}
                </span>
                <span className="mt-1 rounded border border-[var(--line)] px-2 py-0.5 text-xs uppercase tracking-wide text-[var(--ink-3)]">
                  {line.prep_station}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <footer className="border-t border-[var(--line)] p-2">
        {ticket.status === "SUBMITTED" ? (
          <button
            type="button"
            data-testid={`ack-${ticket.order_number}`}
            onClick={() => onAck(ticket)}
            className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)]"
          >
            Start cooking
          </button>
        ) : ticket.status === "PREPARING" ? (
          <button
            type="button"
            data-testid={`all-ready-${ticket.order_number}`}
            onClick={() => onAllReady(ticket)}
            className="min-h-16 w-full rounded-lg bg-[var(--accent)] text-xl font-bold text-[var(--accent-ink)]"
          >
            All ready
          </button>
        ) : (
          <button
            type="button"
            data-testid={`served-${ticket.order_number}`}
            onClick={() => onServed(ticket)}
            className="min-h-16 w-full rounded-lg border-2 border-[var(--accent-line)] text-xl font-bold text-[var(--accent)]"
          >
            Picked up
          </button>
        )}
      </footer>
    </article>
  );
}
