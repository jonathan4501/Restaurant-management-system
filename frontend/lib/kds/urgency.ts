/**
 * Ticket age and what it means. The whole point of the kitchen display: a late ticket must be
 * unmistakable from across the room, and the age must never come from the tablet's own clock —
 * a device with a wrong clock would show every ticket as an hour late, or as brand new.
 */

export type Urgency = "fresh" | "warning" | "late";

export const WARNING_AFTER_SECONDS = 10 * 60;
export const LATE_AFTER_SECONDS = 15 * 60;

/** serverNow − clientNow, from a response `Date` header. Add it to Date.now() for server time. */
export function serverOffsetMs(dateHeader: string | null, clientNow: number = Date.now()): number {
  if (!dateHeader) return 0;
  const serverNow = Date.parse(dateHeader);
  return Number.isNaN(serverNow) ? 0 : serverNow - clientNow;
}

export function ageSeconds(since: string | null, now: number, offsetMs = 0): number {
  if (!since) return 0;
  const started = Date.parse(since);
  if (Number.isNaN(started)) return 0;
  return Math.max(0, Math.floor((now + offsetMs - started) / 1000));
}

export function urgencyFor(seconds: number): Urgency {
  if (seconds >= LATE_AFTER_SECONDS) return "late";
  if (seconds >= WARNING_AFTER_SECONDS) return "warning";
  return "fresh";
}

/** mm:ss, and hh:mm:ss once a ticket has been standing for an hour (it happens; show the truth). */
export function formatAge(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const secs = safe % 60;
  const mm = String(hours > 0 ? minutes : Math.floor(safe / 60)).padStart(2, "0");
  const ss = String(secs).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
}

/** New tickets age from when the waiter sent them; cooking tickets from when the kitchen took them. */
export function ticketClockStart(ticket: {
  status: string;
  submitted_at: string | null;
  acknowledged_at: string | null;
}): string | null {
  if (ticket.status === "PREPARING") return ticket.acknowledged_at ?? ticket.submitted_at;
  if (ticket.status === "READY") return ticket.acknowledged_at ?? ticket.submitted_at;
  return ticket.submitted_at;
}
