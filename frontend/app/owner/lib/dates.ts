/** Business dates for Accra (cutover 04:00). YYYY-MM-DD strings for `from`/`to` query params. */

const ACCRA = "Africa/Accra";
const CUTOVER_HOUR = 4;

function accraParts(now: Date): { y: number; m: number; d: number; hour: number } {
  const fmt = new Intl.DateTimeFormat("en-GB", {
    timeZone: ACCRA,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hourCycle: "h23",
  });
  const parts = Object.fromEntries(fmt.formatToParts(now).map((p) => [p.type, p.value]));
  return {
    y: Number(parts.year),
    m: Number(parts.month),
    d: Number(parts.day),
    hour: Number(parts.hour),
  };
}

function ymd(y: number, m: number, d: number): string {
  return `${y.toString().padStart(4, "0")}-${m.toString().padStart(2, "0")}-${d.toString().padStart(2, "0")}`;
}

/** Current business date in Accra (rolls at 04:00). */
export function businessDateAccra(now: Date = new Date()): string {
  const p = accraParts(now);
  // Before cutover, still yesterday's business date.
  const utc = Date.UTC(p.y, p.m - 1, p.d);
  const shifted = p.hour < CUTOVER_HOUR ? utc - 86_400_000 : utc;
  const d = new Date(shifted);
  return ymd(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

/** Inclusive window of `days` business dates ending on `end` (default: today). */
export function lastNBusinessDates(
  days: number,
  end: string = businessDateAccra(),
): { from: string; to: string } {
  const [y, m, d] = end.split("-").map(Number);
  const endUtc = Date.UTC(y!, m! - 1, d!);
  const startUtc = endUtc - (days - 1) * 86_400_000;
  const start = new Date(startUtc);
  return {
    from: ymd(start.getUTCFullYear(), start.getUTCMonth() + 1, start.getUTCDate()),
    to: end,
  };
}

export function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-GB", {
    timeZone: ACCRA,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
}

export function formatHourLabel(hour: number): string {
  return `${hour.toString().padStart(2, "0")}:00`;
}
