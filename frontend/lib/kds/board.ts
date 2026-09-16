/**
 * What the board shows the instant a cook taps, before the server has confirmed. The kitchen is the
 * one screen where a round trip over a bad connection is unacceptable: the cook has already put the
 * plate on the pass. The card keeps a pending outline until the stream (or the next read) agrees.
 *
 * Pure so the moves can be tested without a browser.
 */

import type { KdsTicket, OrderItemStatus, TicketLine } from "@/lib/domain";

const FINISHED: OrderItemStatus[] = ["READY", "SERVED", "VOIDED"];

function isFinished(line: TicketLine): boolean {
  return FINISHED.includes(line.status);
}

/** New → Preparing. The clock switches to `acknowledged_at`, so it has to be set here too. */
export function ackTicket(ticket: KdsTicket, serverNowIso: string): KdsTicket {
  if (ticket.status !== "SUBMITTED") return ticket;
  return { ...ticket, status: "PREPARING", acknowledged_at: ticket.acknowledged_at ?? serverNowIso };
}

/** One line done. The server emits ORDER_READY when the last one lands, so mirror that here. */
export function markLineReady(ticket: KdsTicket, itemId: string, serverNowIso: string): KdsTicket {
  const items = ticket.items.map((line) =>
    line.item_id === itemId ? { ...line, status: "READY" as OrderItemStatus } : line,
  );
  if (!items.every(isFinished)) return { ...ticket, items };
  return { ...ticket, items, status: "READY", ready_at: ticket.ready_at ?? serverNowIso };
}

export function markAllReady(ticket: KdsTicket, serverNowIso: string): KdsTicket {
  return {
    ...ticket,
    status: "READY",
    ready_at: ticket.ready_at ?? serverNowIso,
    items: ticket.items.map((line) =>
      isFinished(line) ? line : { ...line, status: "READY" as OrderItemStatus },
    ),
  };
}

export function patchTicket(
  rows: KdsTicket[],
  orderId: string,
  change: (ticket: KdsTicket) => KdsTicket,
): KdsTicket[] {
  return rows.map((ticket) => (ticket.order_id === orderId ? change(ticket) : ticket));
}

/** Served tickets leave the board — the food is on the table, the bill is the cashier's problem. */
export function removeTicket(rows: KdsTicket[], orderId: string): KdsTicket[] {
  return rows.filter((ticket) => ticket.order_id !== orderId);
}

/** Server time as an ISO string, from the stream's measured offset. Never the device clock alone. */
export function serverNowIso(offsetMs: number, clientNow: number = Date.now()): string {
  return new Date(clientNow + offsetMs).toISOString();
}
